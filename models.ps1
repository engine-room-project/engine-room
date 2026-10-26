# Shared model planning only: no provider defaults, offers, credentials or rental actions.
$script:EngineRoomModelRoot = $PSScriptRoot

function ValidateModelFiles($settings) {
    $python = Get-Command python -ErrorAction Stop
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $python.Source
    $info.Arguments = '"' + (Join-Path $script:EngineRoomModelRoot 'engine_room/model_validation.py') + '"'
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $outTask = $process.StandardOutput.ReadToEndAsync()
        $errTask = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.WriteLine(($settings | ConvertTo-Json -Depth 5 -Compress))
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(10000)) { $process.Kill(); [void]$process.WaitForExit(2000); throw 'Model validation did not finish. Nothing will be rented.' }
        $output = $outTask.GetAwaiter().GetResult()
        $ignored = $errTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw 'The selected model filenames or shard set are invalid. Nothing will be rented.' }
        $output | ConvertFrom-Json
    } finally { $process.Dispose() }
}

function ValidateGgufFiles($files, [string]$mmproj = '') {
    ValidateModelFiles @{engine='llama.cpp';files=@($files);mmproj=$mmproj}
}

function ModelId([string]$value) {
    $id = $value.Trim()
    if ($id -match '^https?://(?!huggingface\.co/)') {
        throw 'Use a Hugging Face model page or owner/model name, without extra paths or query text.'
    }
    $id = $id -replace '^https?://huggingface\.co/', ''
    $id = $id -replace '[\?#].*$', ''
    $id = $id.TrimEnd('/')
    $id = $id -replace '/(tree|blob|resolve|discussions|commits)(/.*)?$', ''
    $id = $id.TrimEnd('/')
    if ($id -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$' -or $id.Contains('..')) {
        throw 'Use a Hugging Face model page or owner/model name, without extra paths or query text.'
    }
    $id
}

function ModelPlan($id, $info, $config) {
    $id = ModelId $id
    if ($info.sha -notmatch '^[a-fA-F0-9]{40}$') { throw 'The model revision could not be verified. Nothing will be rented.' }
    $c = if ($config.text_config) { $config.text_config } else { $config }
    $native = [long]$c.max_position_embeddings
    # Each launch checks the capacity its tool needs (ToolMinContext); the model itself only needs a usable minimum.
    if ($native -lt 8192) { throw 'This model does not publish a usable conversation capacity. Nothing will be rented.' }
    $kvElements = KvElements $c
    $files = @($info.siblings | Where-Object { $_.rfilename -match '^[^/]+\.safetensors$' -and $_.rfilename -notmatch 'adapter' })
    if (-not $files.Count) { throw 'Choose a model with safetensors weights. GGUF and adapter-only repositories are not supported here.' }
    [double]$bytes = 0
    foreach ($f in $files) {
        if (-not $f.size -or [double]$f.size -le 0) { throw 'The published weight sizes are missing. Nothing will be rented.' }
        $bytes += [double]$f.size
    }
    $quant = $config.quantization_config
    if (-not $quant) { $quant = $c.quantization_config }
    if ($quant -and $quant.quant_method -notin 'awq','gptq','fp8','compressed-tensors') { throw 'This published quantization format has not been checked for this launcher.' }
    $dtype = @($c.dtype, $c.torch_dtype, $config.dtype, $config.torch_dtype | Where-Object { $_ }) | Select-Object -First 1
    if ($dtype -notin 'float16','bfloat16','float32') { throw 'The published precision is missing or unsupported. Nothing will be rented.' }
    $kvElementBytes = if ($dtype -eq 'float32') { 4 } else { 2 }
    $fileSizes = @{}; $fileHashes = @{}
    foreach ($f in $files) {
        $fileSizes[[string]$f.rfilename] = [long]$f.size
        if ($f.lfs.sha256 -cmatch '^[a-f0-9]{64}$') { $fileHashes[[string]$f.rfilename] = [string]$f.lfs.sha256 }
    }
    [void](ValidateModelFiles @{engine='vLLM';fileSizes=$fileSizes})
    $family = [string]$config.model_type
    $tool, $reasoning = ModelFamily $family
    $efforts = FamilyEfforts $family
    [pscustomobject]@{
        id = $id; revision = $info.sha; weightBytes = $bytes; engine = 'vLLM'; fileSizes = $fileSizes; fileHashes = $fileHashes
        dtype = $dtype
        kvBytesPerToken = [double]($kvElements * $kvElementBytes)
        overheadBytes = [Math]::Max(4GB, $bytes * 0.10)
        nativeContext = $native; context = [Math]::Min(1048576, $native); tool = $tool; reasoning = $reasoning; efforts = $efforts; vision = [bool]($config.vision_config -or $c.vision_config)
        quality = $(if ($quant) { "Published $($quant.quant_method) weights; no further shrinking" } else { 'Published precision; no shrinking' })
        warning = $(if (-not $tool) { 'Experimental: tool use is unverified for this family; it may chat but not edit files.' } else { 'Experimental: metadata checked; this model and tool combination has not passed release validation.' })
    }
}

# Values cached per token: keys and values for every attention layer (linear layers keep a fixed state).

function KvElements($c) {
    if ($c.kv_lora_rank -or $c.model_type -match 'deepseek') { throw 'This model uses a different memory layout. Its fit cannot yet be checked safely.' }
    $layers = [int]$c.num_hidden_layers; $heads = [int]$c.num_key_value_heads
    $dim = [int]$c.head_dim
    if (-not $dim -and $c.num_attention_heads) { $dim = [int]($c.hidden_size / $c.num_attention_heads) }
    if ($layers -le 0 -or $heads -le 0 -or $dim -le 0) { throw 'The model does not publish enough information to estimate memory safely.' }
    if ($c.layer_types) {
        if (@($c.layer_types).Count -ne $layers -or @($c.layer_types | Where-Object { $_ -notin 'full_attention','linear_attention','sliding_attention' }).Count) {
            throw 'This model has an unfamiliar memory layout. Nothing will be rented.'
        }
        # Linear state uses the overhead reserve; sliding layers are conservatively counted as full.
        $layers = @($c.layer_types | Where-Object { $_ -ne 'linear_attention' }).Count
    }
    if ($layers -le 0) { throw 'This model has no supported attention layout for the memory estimate.' }
    [double](2 * $layers * $heads * $dim)
}

# Tool-call and reasoning parsers by model family (vLLM names; llama.cpp reads the chat template instead).

function ModelFamily([string]$family) {
    switch -Regex ($family) {
        '^qwen3_[5-9]' { return 'qwen3_xml', 'qwen3' }
        '^qwen3' { return 'hermes', 'qwen3' }
        '^qwen2' { return 'hermes', '' }
        '^llama' { return 'llama3_json', '' }
        '^mistral' { return 'mistral', '' }
    }
    return '', ''
}

function BaseModelId($info) { try { ModelId ([string](@($info.cardData.base_model) | Select-Object -First 1)) } catch { '' } }

# Effort levels the chat template accepts for this family (Qwen 3.5+ answers xhigh by default); none turns
# thinking off. vLLM and llama.cpp both hand the level to the model's own chat template.

function FamilyEfforts([string]$family) { if ($family -match '^qwen3_[5-9]') { @('low','medium','xhigh') } else { @() } }

# A GGUF chat model runs on llama.cpp. GGUF repositories rarely publish a settings file, so the memory
# layout comes from the base model they name; the size comes from the chosen version's files.

function GgufPlan($id, $info, $baseConfig, [string]$variantName = '') {
    $id = ModelId $id
    if ($info.sha -notmatch '^[a-fA-F0-9]{40}$') { throw 'The model revision could not be verified. Nothing will be rented.' }
    $d = DescribeCheckpoint $info
    if ($d.task -notin 'text-generation','image-text-to-text','') { throw "Engine Room runs GGUF chat models only; this one is for $($d.kind.ToLower())." }
    $complete = @($d.variants | Where-Object complete)
    $v = if ($variantName) { @($complete | Where-Object name -eq $variantName) | Select-Object -First 1 } else { $complete | Select-Object -First 1 }
    if (-not $v) { throw 'The chosen version is missing or incomplete. Add the model again and choose another version.' }
    if (-not $v.sizesKnown) { throw 'The published file sizes are missing. Nothing will be rented.' }
    if (-not $baseConfig) { throw 'This model does not name a base model with published settings, so its memory needs cannot be estimated safely.' }
    $c = if ($baseConfig.text_config) { $baseConfig.text_config } else { $baseConfig }
    $kvElements = KvElements $c
    $native = [long]$info.gguf.context_length
    if ($native -le 0) { $native = [long]$c.max_position_embeddings }
    if ($native -lt 8192) { throw 'This model does not publish a usable conversation capacity. Nothing will be rented.' }
    # Vision needs its projector file; prefer 16-bit, then any other.
    $mmproj = $null
    if ($d.vision) {
        $projectors = @($info.siblings | Where-Object { $_.rfilename -match '(?i)mmproj.*\.gguf$' -and $_.size -gt 0 })
        $mmproj = @(@($projectors | Where-Object rfilename -match '(?i)(^|[-_.])F16[-_.]') + @($projectors | Where-Object rfilename -match '(?i)BF16') + $projectors) | Select-Object -First 1
    }
    $validated = ValidateGgufFiles @($v.files) $(if ($mmproj) { [string]$mmproj.rfilename } else { '' })
    $tool, $reasoning = ModelFamily ([string]$baseConfig.model_type)
    $weights = $v.bytes + $(if ($mmproj) { [double]$mmproj.size } else { 0 })
    $fileSizes = @{}; $fileHashes = @{}
    foreach ($f in $info.siblings | Where-Object { $_.rfilename -in @($v.files) -or ($mmproj -and $_.rfilename -eq $mmproj.rfilename) }) {
        $fileSizes[[string]$f.rfilename] = [long]$f.size
        if ($f.lfs.sha256 -cmatch '^[a-f0-9]{64}$') { $fileHashes[[string]$f.rfilename] = [string]$f.lfs.sha256 }
    }
    [pscustomobject]@{
        id = $id; revision = $info.sha; engine = 'llama.cpp'; variant = $v.name; files = @($v.files); mmproj = $(if ($mmproj) { [string]$mmproj.rfilename } else { '' })
        weightBytes = $weights; dtype = 'gguf'; fileSizes = $fileSizes; fileHashes = $fileHashes
        kvBytesPerToken = $kvElements * 2   # llama.cpp keeps its cache in 16-bit values by default
        overheadBytes = [Math]::Max(2GB, $weights * 0.10)
        nativeContext = $native; context = [Math]::Min(1048576, $native); tool = $tool; reasoning = $reasoning; efforts = (FamilyEfforts ([string]$baseConfig.model_type)); vision = [bool]$mmproj
        quality = "$($v.name), a compressed version"
        warning = 'Experimental: metadata checked; this model and tool combination has not passed release validation.'
    }
}

function ModelFit($plan, [double]$gb) {
    if ($gb -le 0 -or -not $plan.kvBytesPerToken) { return 0 }
    $room = [Math]::Floor((($gb * 1GB * 0.92) - $plan.weightBytes - $plan.overheadBytes) / $plan.kvBytesPerToken)
    [long][Math]::Max(0, [Math]::Min(1048576, [Math]::Min($plan.nativeContext, $room)))
}

# Coding tools send whole files and long histories; a plain chat or no tool needs far less.

function ToolMinContext([string]$toolId) { if ($toolId -in 'opencode','codex','claude') { 65536 } else { 8192 } }

function GpuPlan($plan, [double]$gb, [long]$minContext = 8192) {
    $context = ModelFit $plan $gb
    if ($context -lt $minContext) { throw "This GPU fits $([int][Math]::Floor($context / 1024))k of conversation capacity; at least $([int]($minContext / 1024))k is needed. Choose a larger GPU." }
    # Copy the checked metadata so selecting a GPU never changes another run's plan.
    $selected = $plan.PSObject.Copy()
    $selected | Add-Member -NotePropertyName context -NotePropertyValue $context -Force
    $selected
}



function DescribeCheckpoint($info) {
    $tasks = @{
        'text-generation' = 'Text & chat', 'vLLM'; 'image-text-to-text' = 'Text & vision', 'vLLM'
        'text-to-image' = 'Image generation', 'Image engine'; 'image-to-image' = 'Image editing', 'Image engine'
        'text-to-video' = 'Video generation', 'Video engine'; 'image-to-video' = 'Video generation', 'Video engine'
        'automatic-speech-recognition' = 'Speech recognition', 'Audio engine'; 'text-to-speech' = 'Speech generation', 'Audio engine'
        'text-to-audio' = 'Audio generation', 'Audio engine'; 'feature-extraction' = 'Embeddings', 'Embedding engine'
        'sentence-similarity' = 'Embeddings', 'Embedding engine'; 'text-ranking' = 'Reranking', 'Reranking engine'
    }
    $task = [string]$info.pipeline_tag
    $names = @($info.siblings | ForEach-Object { [string]$_.rfilename })
    $kind, $engine = if ($tasks.ContainsKey($task)) { $tasks[$task] } else { 'Type not published', 'Needs identification' }
    $adapter = 'adapter_config.json' -in $names
    $ggufs = @($info.siblings | Where-Object { ([string]$_.rfilename) -match '\.gguf$' })
    if ($adapter) { $kind = 'Adapter (LoRA)'; $engine = 'Needs its base model' }
    elseif ($ggufs.Count -and $task -in 'text-generation','image-text-to-text','') { $engine = 'llama.cpp' }
    # GGUF is a file format, not a task. Vision projector files are companions, never a main model.
    $groups = [ordered]@{}
    foreach ($f in $ggufs | Where-Object { $_.rfilename -notmatch '(?i)mmproj|projector' }) {
        $name = [string]$f.rfilename
        $key = $name; $expected = 1
        if ($name -match '(?i)^(.*)-(\d{5})-of-(\d{5})\.gguf$') { $key = $Matches[1] + '.gguf'; $expected = [int]$Matches[3] }
        if (-not $groups.Contains($key)) { $groups[$key] = [pscustomobject]@{ name = $key; files = @(); bytes = [double]0; sizesKnown = $true; expected = $expected } }
        $g = $groups[$key]; $g.files += $name
        if ($f.size -and [double]$f.size -gt 0) { $g.bytes += [double]$f.size } else { $g.sizesKnown = $false }
    }
    $variants = @(foreach ($g in $groups.Values) {
        $complete = $false
        try { [void](ValidateGgufFiles @($g.files)); $complete = $true } catch { }
        $g | Add-Member -NotePropertyName complete -NotePropertyValue $complete -PassThru |
            Add-Member -NotePropertyName recommended -NotePropertyValue ($complete -and $g.name -match '(?i)Q4_K_M') -PassThru |
            Add-Member -NotePropertyName label -NotePropertyValue ($g.name + ' - ' + $(if ($g.sizesKnown) { '{0:N1} GB' -f ($g.bytes / 1e9) } else { 'size not published' }) + $(if (-not $complete) { ' - incomplete' } elseif ($g.name -match '(?i)Q4_K_M') { ' - suggested start' } else { '' })) -PassThru
    }) | Sort-Object @{ e = { -not $_.recommended } }, name
    $format = if ($ggufs.Count) { 'GGUF' } elseif ($names -match '\.safetensors$') { 'Safetensors' } elseif ($info.library_name) { [string]$info.library_name } else { 'Not published' }
    [pscustomobject]@{ task = $task; kind = $kind; engine = $engine; adapter = $adapter; format = $format; variants = @($variants)
        vision = ($task -eq 'image-text-to-text') }
}

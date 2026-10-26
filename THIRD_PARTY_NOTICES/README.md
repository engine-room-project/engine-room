# Third-party runtime notices

The source package includes the upstream licence texts for the selected llama.cpp,
Hugging Face Hub and vLLM runtime candidates. These are third-party notices, not a
selection of the Engine Room project licence. Required copyright attribution stays intact.

Runtime containers and packages are downloaded from their upstream publishers. Preserve
all licence, NOTICE, copyright and distribution metadata contained in their images,
archives and installed wheel metadata. The bootstrap preserves those files rather than
removing them to reduce size. The llama.cpp release archive's own LICENSE is extracted.

The separate CUDA support archive contains NVIDIA runtime libraries. Its use also depends
on NVIDIA's terms, including the CUDA Toolkit licence and the container's bundled NVIDIA
notices: https://docs.nvidia.com/cuda/archive/12.8.1/eula/index.html . The source package
contains download references/checksums, not redistributed CUDA binaries. Any future binary
bundle or published runtime image needs its own complete redistribution/notice inventory.

Dependencies installed from the locked wheels retain their .dist-info licence metadata.
The vLLM image is immutable and retains its upstream dependency and NVIDIA notices.
A complete final package and runtime notice inspection remains a release gate.


Colab protocol adaptation: google-colab-cli 0.7.5, copyright 2026 Google LLC,
Apache License 2.0. The upstream licence text is preserved in
`google-colab-cli-LICENSE.txt`; the pinned source/wheel evidence is in
`controller/colab-source.json`. The optional controller dependency retains its
own installed notices. Account credentials and upstream CLI state are never bundled.

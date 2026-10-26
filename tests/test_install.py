import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from engine_room.install import inspect_source,install


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.source=self.root/"source"; self.source.mkdir(); self.target=self.root/"installed"
        self.manifest=dict(schema=1,source_commit="a"*40,status="UNPUBLISHED CANDIDATE - OWNER DECISIONS REQUIRED",files=[])
        for name in ("EngineRoom.ps1","desktop/ui.ps1","engine_room/desktop_bridge.py","THIRD_PARTY_NOTICES/README.md"):
            path=self.source/name; path.parent.mkdir(parents=True,exist_ok=True); data=("Synthetic "+name).encode(); path.write_bytes(data)
            self.manifest["files"].append(dict(path=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
        self.save()
    def save(self): (self.source/"SOURCE_MANIFEST.json").write_text(json.dumps(self.manifest),encoding="utf-8")
    def test_verified_install_preserves_bytes_and_external_state_without_copying_extra_files(self):
        state=self.root/"existing-state"; state.mkdir(); (state/"keep.json").write_text("Keep original evidence")
        (self.source/"untracked-secret.json").write_text("Do not copy")
        receipt=install(self.source,self.target)
        self.assertEqual("a"*40,receipt["source_commit"])
        self.assertEqual("Keep original evidence",(state/"keep.json").read_text())
        self.assertFalse((self.target/"untracked-secret.json").exists())
        for item in self.manifest["files"]: self.assertEqual((self.source/item["path"]).read_bytes(),(self.target/item["path"]).read_bytes())
        self.assertEqual(receipt,json.loads((self.target/"installation.json").read_text()))
        with self.assertRaises(ValueError): install(self.source,self.target)
    def test_altered_source_refuses_before_creating_destination(self):
        (self.source/"EngineRoom.ps1").write_bytes(b"Changed")
        with self.assertRaises(ValueError): install(self.source,self.target)
        self.assertFalse(self.target.exists())
    def test_unsafe_case_colliding_or_receipt_paths_refuse_before_copy(self):
        original=list(self.manifest["files"])
        for name in ("../outside","/absolute","C:/outside","desktop/../outside","desktop\\outside","README.","installation.json","Source_Manifest.json","engineroom.ps1"):
            with self.subTest(name=name):
                self.manifest["files"]=original+[dict(path=name,sha256="0"*64,bytes=0)]; self.save()
                with self.assertRaises(ValueError): install(self.source,self.target)
                self.assertFalse(self.target.exists())
    def test_source_and_destination_cannot_nest(self):
        with self.assertRaises(ValueError): install(self.source,self.source/"copy")
        self.assertFalse((self.source/"copy").exists())
    @unittest.skipUnless(os.name=="posix","Unix symlink fixture")
    def test_linked_destination_parent_cannot_create_unrelated_directories(self):
        outside=self.root/"outside"; outside.mkdir(); alias=self.root/"alias"; alias.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError): install(self.source,alias/"unrelated"/"install")
        self.assertEqual([],list(outside.iterdir()))
    @unittest.skipUnless(os.name=="posix","Unix symlink fixture")
    def test_source_symlink_is_refused_even_when_bytes_match(self):
        entry=self.source/"EngineRoom.ps1"; outside=self.root/"outside"; entry.rename(outside); entry.symlink_to(outside)
        with self.assertRaises(ValueError): install(self.source,self.target)
        self.assertFalse(self.target.exists())

    @unittest.skipUnless(os.name=="nt","Native Windows installer and shortcut")
    def test_native_installer_creates_only_new_source_and_selected_shortcut(self):
        checkout=Path(__file__).resolve().parents[1]
        for name in ("Install-EngineRoom.ps1","engine_room/install.py"):
            data=(checkout/name).read_bytes(); (self.source/name).write_bytes(data)
            self.manifest["files"].append(dict(path=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
        self.save(); shortcut_dir=self.root/"shortcuts"; shortcut_dir.mkdir()
        environment=dict(os.environ); environment["PATH"]=str(Path(sys.executable).parent)+os.pathsep+environment["PATH"]
        command=["powershell.exe","-NoProfile","-File",str(self.source/"Install-EngineRoom.ps1"),"-Destination",str(self.target),"-ShortcutDirectory",str(shortcut_dir)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=30,env=environment)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        links=list(shortcut_dir.glob("*.lnk")); self.assertEqual(1,len(links))
        reader=self.root/"read-link.ps1"
        reader.write_text("param($Path)\n$link=(New-Object -ComObject WScript.Shell).CreateShortcut($Path)\n@{target=$link.TargetPath;arguments=$link.Arguments;directory=$link.WorkingDirectory}|ConvertTo-Json -Compress",encoding="utf-8")
        read=subprocess.run(["powershell.exe","-NoProfile","-File",str(reader),str(links[0])],capture_output=True,text=True,timeout=15)
        self.assertEqual(0,read.returncode,read.stderr); actual=json.loads(read.stdout)
        self.assertEqual(str(self.target),actual["directory"])
        self.assertEqual('-NoProfile -STA -File "'+str(self.target/"EngineRoom.ps1")+'"',actual["arguments"])
        self.assertTrue(actual["target"].lower().endswith("powershell.exe"))
        before=(self.target/"EngineRoom.ps1").read_bytes()
        repeat=subprocess.run(command,capture_output=True,text=True,timeout=30,env=environment)
        self.assertNotEqual(0,repeat.returncode); self.assertEqual(before,(self.target/"EngineRoom.ps1").read_bytes())

"""Package boundaries use real isolated Git history and ZIP artifacts."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from scripts.release.build_source import build,REQUIRED


@unittest.skipUnless(shutil.which("git"),"Git builds committed source candidates")
class SourcePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"repo"; self.root.mkdir()
        self.git("init","--quiet")
        for name in REQUIRED:
            path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text("Synthetic "+name+"\n",encoding="utf-8")
        (self.root/"WORKLOG.md").write_text("Development notes must not ship.",encoding="utf-8")
        self.git("add","."); self.commit()
    def git(self,*args,input=None):
        return subprocess.check_output(["git","-C",str(self.root),*args],input=input,stderr=subprocess.PIPE)
    def commit(self):
        self.git("-c","user.name=Engine Room Tests","-c","user.email=tests@engine-room.invalid","commit","--quiet","-m","test: prepare synthetic source")
    def test_reproducible_archive_uses_committed_bytes_and_preserves_notices(self):
        (self.root/"README.md").write_text("Uncommitted replacement",encoding="utf-8")
        (self.root/"engine_room"/"local-state.json").write_text("Untracked state",encoding="utf-8")
        one=Path(self.temp.name)/"one.zip"; two=Path(self.temp.name)/"two.zip"
        manifest=build(self.root,one); build(self.root,two)
        self.assertEqual(one.read_bytes(),two.read_bytes())
        with zipfile.ZipFile(one) as archive:
            self.assertNotIn("engine-room-source/WORKLOG.md",archive.namelist())
            self.assertNotIn("engine-room-source/engine_room/local-state.json",archive.namelist())
            for item in manifest["files"]:
                data=archive.read("engine-room-source/"+item["path"])
                self.assertEqual(item["sha256"],hashlib.sha256(data).hexdigest())
                self.assertEqual(item["bytes"],len(data))
            self.assertEqual(b"Synthetic README.md\n",archive.read("engine-room-source/README.md"))
            self.assertEqual(manifest,json.loads(archive.read("engine-room-source/SOURCE_MANIFEST.json")))
        with self.assertRaises(FileExistsError): build(self.root,one)
    def test_tracked_runtime_state_inside_product_scope_is_rejected(self):
        state=self.root/"engine_room"/"credentials"/"unexpected.json"; state.parent.mkdir(); state.write_text("Synthetic",encoding="utf-8")
        self.git("add","."); self.commit()
        with self.assertRaises(ValueError): build(self.root,Path(self.temp.name)/"bad.zip")
    def test_git_symlink_inside_product_scope_is_rejected_without_following_it(self):
        oid=self.git("hash-object","-w","--stdin",input=b"../../outside").decode().strip()
        self.git("update-index","--add","--cacheinfo","120000",oid,"engine_room/linked.py"); self.commit()
        with self.assertRaises(ValueError): build(self.root,Path(self.temp.name)/"link.zip")
    def test_missing_required_notice_blocks_candidate(self):
        self.git("rm","THIRD_PARTY_NOTICES/vllm-LICENSE.txt"); self.commit()
        with self.assertRaises(ValueError): build(self.root,Path(self.temp.name)/"missing.zip")

"""Exercise existing-package registration against temporary package bytes. No build or runtime is started."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REGISTER = Path(__file__).with_name('register-build-identity.ps1')
POWERSHELL = shutil.which('powershell.exe') or shutil.which('pwsh.exe')


@unittest.skipUnless(os.name=='nt' and POWERSHELL,'Windows package registration')
class NumberedReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.target=self.root/'release-r9/BetterGI-English-win-x64'
        self.target.mkdir(parents=True)
        self.hashes=[]
        for name,binary in [('BetterGI.exe',b'executable fixture'),('BetterGI.dll',b'assembly fixture')]:
            (self.target/name).write_bytes(binary)
            self.hashes.append(dict(File=name,Algorithm='SHA256',Hash=hashlib.sha256(binary).hexdigest().upper()))
        self.stamp=dict(sourceCommit='a'*40,sdk='10.0.402',runtime='win-x64',selfContained=True)
        self.manifest=self.target.parent/'build-manifest.json'
        self.witness=self.root/'release-retention/package-witnesses/release-r9'

    def english(self,**evidence):
        (self.target/'Build-Source.json').write_text(json.dumps(dict(self.stamp,**evidence)))
        (self.target/'Build-SHA256.json').write_text(json.dumps(self.hashes))

    def register(self,*args,success=True):
        completed=subprocess.run([POWERSHELL,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
            str(REGISTER),'-TargetDirectory',str(self.target),*args],text=True,capture_output=True,timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(completed.returncode==0,success,completed.stderr)

    def test_english_tested_identity_witness_and_idempotent_retry(self):
        self.english(workingTreeDirty=False,validationConfiguration='Release',validationKind='english-tests')
        self.register('-PreserveWitness')
        initial=self.manifest.read_bytes()
        manifest=json.loads(initial)
        self.assertEqual(manifest['validationConfiguration'],'Release')
        self.assertEqual(manifest['validationKind'],'english-tests')
        self.assertIs(manifest['workingTreeDirty'],False)
        self.assertEqual(Path(manifest['targetDirectory']),self.target)
        for row in self.hashes:
            suffix=row['File'].split('.')[1]
            self.assertEqual(manifest[suffix+'Sha256'],row['Hash'].lower())
            self.assertEqual((self.witness/self.target.name/row['File']).read_bytes(),(self.target/row['File']).read_bytes())
        self.assertEqual((self.witness/'build-manifest.json').read_bytes(),initial)
        self.manifest.unlink()
        self.register('-PreserveWitness')
        self.assertEqual(self.manifest.read_bytes(),initial)
        (self.target/'BetterGI.dll').write_bytes(b'different assembly')
        self.register('-PreserveWitness',success=False)
        self.assertEqual(self.manifest.read_bytes(),initial)

    def test_older_english_export_has_unknown_validation_and_dirty_state(self):
        self.english()
        self.register()
        manifest=json.loads(self.manifest.read_bytes())
        self.assertIsNone(manifest['workingTreeDirty'])
        self.assertIsNone(manifest['validationConfiguration'])
        self.assertIsNone(manifest['validationKind'])
        self.assertFalse(self.witness.exists())

    def test_rdp_build_passes_explicit_debug_validation_and_selected_publish_mode(self):
        self.register('-SourceRevision',self.stamp['sourceCommit'],'-SdkVersion',self.stamp['sdk'],
                      '-PublishConfiguration','Debug','-ValidationConfiguration','Debug','-ValidationKind','solution-build')
        manifest=json.loads(self.manifest.read_bytes())
        self.assertEqual((manifest['publishConfiguration'],manifest['validationConfiguration'],manifest['validationKind']),
                         ('Debug','Debug','solution-build'))
        self.register('-SourceRevision','b'*40,'-SdkVersion',self.stamp['sdk'],success=False)
        self.assertEqual(json.loads(self.manifest.read_bytes()),manifest)

    def test_english_publisher_calls_registration_only_for_numbered_exports(self):
        repo=self.root/'fixture-repo'
        script=repo/'Build/Scripts/publish-english.ps1'
        script.parent.mkdir(parents=True)
        shutil.copyfile(REGISTER.parents[2]/'Build/Scripts/publish-english.ps1',script)
        helper=repo/'tools/rdp-automation'/REGISTER.name
        helper.parent.mkdir(parents=True)
        shutil.copyfile(REGISTER,helper)
        for name in ('LICENSE','Docs/English-Build.txt','Docs/Local-Setup.txt','Build/Scripts/manage-release-retention.ps1',
                     'tools/quest-pilot/check-storage-headroom.ps1','Build/EnglishWeb/dist/Map/Editor/index.html',
                     'Build/EnglishWeb/dist/Web/ScriptRepo/index.html'):
            path=repo/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.touch()
        web=repo/'Build/EnglishWeb'
        for name in ('README.md','source.json','build.ps1','floor-names.json','floor-name-notes.md','patches','licenses'):
            (web/name).touch()
        harness=repo/'mock-publish.ps1'
        harness.write_text('''param($Publish,$OutputPath,$Skip)
$ErrorActionPreference = 'Stop'
function global:git {
    $global:LASTEXITCODE = 0
    if ($args -contains 'rev-parse') { 'a' * 40 }
    elseif ($args -contains 'status') { ' M tracked-file' }
}
function global:FakeDotNet {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq '--version') { '10.0.402' }
    if ($args[0] -eq 'publish') {
        $target = $args[[Array]::IndexOf($args,'-o') + 1]
        [IO.Directory]::CreateDirectory($target) | Out-Null
        foreach ($name in 'BetterGI.exe','BetterGI.dll') { [IO.File]::WriteAllText((Join-Path $target $name),$name) }
    }
}
& $Publish -DotNet FakeDotNet -OutputDirectory $OutputPath -SkipTests:($Skip -eq 'yes')
''')
        for name,skip in [('release-r11/BetterGI-English-win-x64',False),('release-r12/BetterGI-English-win-x64',True),
                          ('portable',True)]:
            output=repo/'artifacts'/name
            result=subprocess.run([shutil.which('pwsh.exe') or POWERSHELL,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
                                   str(harness),str(script),str(output),'yes' if skip else 'no'],text=True,
                                   capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode,0,result.stderr)
            manifest=output.parent/'build-manifest.json'
            self.assertTrue((output/'Build-Source.json').is_file())
            if name=='portable':
                self.assertFalse(manifest.exists())
                continue
            actual=json.loads(manifest.read_bytes())
            self.assertIs(actual['workingTreeDirty'],True)
            self.assertEqual(actual['validationConfiguration'],None if skip else 'Release')
            self.assertTrue((repo/'artifacts/release-retention/package-witnesses'/output.parent.name/'build-manifest.json').is_file())


if __name__=='__main__':
    unittest.main()

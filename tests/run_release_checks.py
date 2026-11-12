import sys,unittest,importlib,json,time
from pathlib import Path
p=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(p),str(p/'tests/reliability')]
for name in ('api_client','structured_output','pedagogical_runtime','agent','study_protocol','tutor_actions','stage_tracker','research_runtime','space_bridge','failure_records','reply_flow'):
 m=importlib.import_module(name);assert Path(m.__file__).parent==p,name
suite=unittest.TestSuite();suite.addTests(unittest.defaultTestLoader.discover(str(p/'tests/reliability'),pattern='test_*.py'))
for f in ('test_research_system','test_research_web','test_research_policy','test_research_ablations','test_space_bridge','test_sqlserver_store','test_web_hosting','test_student_assets'):
 spec=importlib.util.spec_from_file_location(f,p/'tests/regression'/f'{f}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(m))
old=p/'tests/protocol'
sys.path.append(str(old))
for f in old.glob('test_*.py'):
 spec=importlib.util.spec_from_file_location(f.stem,f);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(m))
r=unittest.TextTestRunner(verbosity=1).run(suite)
report={'tests_run':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),'passed':r.wasSuccessful(),'scope':'local tests; inference mocked except previously recorded live evidence','runtime_imports_verified':True}
print(json.dumps(report));raise SystemExit(0 if r.wasSuccessful() else 1)

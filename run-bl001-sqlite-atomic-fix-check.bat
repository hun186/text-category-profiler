@echo off
setlocal
cd /d "%~dp0"
rem KI-012: PRIVATE SQLite atomic-writer acceptance, never use WorkPool or real DB.
rem Full crash probe uses a disposable subprocess and expects PASS_ATOMICITY.
python -m unittest -v tests.test_bl001_stage_sql_atomic_fix tests.test_bl001_stage_sql_shared tests.test_bl001_df_sql_provider_contracts
if errorlevel 1 goto fail
python -m scripts.bl001_stage_sqlite_atomicity_probe
if errorlevel 1 goto fail
python -m scripts.bl001_stage_sqlite_lock_acceptance
if errorlevel 1 goto fail
echo STATUS=PASS_KI012_PRIVATE
exit /b 0
:fail
echo STATUS=FAIL_KI012_PRIVATE
exit /b 1

@echo off
rem SHW 3DLAB (poste de dev) : meme lanceur que les installations
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (start "" ".venv\Scripts\pythonw.exe" shw3dlab.pyw) else (start "" "%~dp0..\DAVINBOT-V2\.venv\Scripts\pythonw.exe" shw3dlab.pyw)

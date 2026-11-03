@echo off
setlocal
set "AI_CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%AI_CSC%" exit /b 1
"%AI_CSC%" /nologo /codepage:65001 /target:winexe /platform:x64 /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll /out:"%~dp0..\..\..\..\AI-Otomatik-Egitim.exe" "%~dp0TrainingLauncher.cs"
exit /b %ERRORLEVEL%

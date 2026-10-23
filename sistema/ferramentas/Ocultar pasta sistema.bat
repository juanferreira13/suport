@echo off
rem Oculta a pasta "sistema" (ela continua funcionando; so nao aparece no Explorador de Arquivos).
for %%I in ("%~dp0..") do attrib +h "%%~fI"
echo A pasta "sistema" foi ocultada.
pause

@echo off
rem Deixa a pasta "sistema" visivel no Explorador de Arquivos.
for %%I in ("%~dp0..") do attrib -h "%%~fI"
echo A pasta "sistema" agora aparece na pasta do projeto.
pause

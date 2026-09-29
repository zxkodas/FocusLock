---
name: Bug
about: Algo no funciona
title: ""
labels: bug
assignees: ""
---

## Qué pasa

Contá qué hiciste y qué pasó en vez de lo que esperabas.

## Cómo lo reproducís

Si es un bloqueo, el orden importa: qué programa, con qué configuración, y en
qué momento.

## Diagnóstico

Pegá la salida de esto primero. Cubre el servicio, las claves IFEO, el pipe, el
servidor HTTP y si la copia instalada difiere de tu carpeta de trabajo:

```
python -m focuslock doctor
```

Si el problema es la extensión del navegador, avisá cuál (Chrome o Firefox) y
qué dice la consola.

## Entorno

- Windows:
- TickFence (el de *Ajustes → General*, o `python -m focuslock status`):
- Python: `python --version`
- ¿Instalado con el `.exe` o con `install.ps1`?:

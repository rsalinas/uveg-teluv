# Instruccions del repositori

## Context del projecte

Eina CLI per a gestionar el desviament de trucades al portal Cisco Unified
Communications Self Care (UCSC Portal, versió 15) de la Universitat de València.
L'eina automatitza les operacions de desviament (`f`), desactivació (`uf`) i
consulta d'estat (`check`) contra l'API REST UCM-UDS a `pubburjs1.tel.uv.es`.

## Llengua

Aquest és un projecte de la universitat i s'escriu en valencià.

- Tota la prosa va en valencià: documentació, comentaris, docstrings, textos
  d'ajuda, missatges a l'usuari i missatges de commit.
- Els identificadors de codi (noms de variables, funcions i mòduls) es mantenen
  en anglés, per convenció i portabilitat.

## Commits

- Fes commits conforme es vagen acabant les tasques, no en bloc.
- Cada commit ha de tindre un objectiu clar i acotat.
- Usa missatges de commit breus i descriptius, en valencià.

## Operativa recomanada

- Valida primer en mode `--dry-run` sempre que siga possible.
- No mostres mai secrets en la documentació ni en l'eixida de comandes.

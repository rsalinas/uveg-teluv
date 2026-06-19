# teluv

Eina CLI en Python per a gestionar el desviament del telefon Cisco de la UV.

## Objectiu

Proporcionar una ordre simple:

- `teluv` (o `teluv check`) — mostra l'estat actual del desviament
- `teluv f [NUMERO]` — activa el desviament general
- `teluv uf` — desactiva el desviament general

Sense arguments, mostra l'estat actual.

## Requisits

- Python 3.9+
- requests
- argcomplete

Instal_lacio rapida:

```bash
python3 -m pip install requests argcomplete
chmod +x teluv
ln -s "$PWD/teluv" ~/bin/teluv   # o on tingues el PATH
```

## Configuracio inicial

La primera vegada, executa `init`. Et demanara usuari i contrasenya de la UV,
**els verificara contra el servidor en l'acte** i, opcionalment, un numero de
desviament per defecte. Ho guarda tot en `~/.uv_ldap_secrets` (permisos 600):

```bash
teluv init
```

No cal editar cap fitxer a ma: la ferramenta el genera. L'extensio del telefon
es descobreix automaticament.

Si ho prefereixes, pots saltar-te `init` i passar les credencials per variables
d'entorn `TELUV_USER` i `TELUV_PASSWORD`, que tenen preferencia sobre el fitxer.

## Us basic

Activar desviament a un numero concret:

```bash
teluv f 0612345678
```

Activar desviament al numero per defecte (`default_destination`):

```bash
teluv f
```

Els ultims numeros usats es guarden i es mostren en l'estat (`Recent destinations`).

Desactivar desviament general:

```bash
teluv uf
```

Consultar l'estat actual del desviament:

```bash
teluv          # o teluv check
```

Veure que enviaria sense tocar res (prova segura):

```bash
teluv --dry-run f
teluv --dry-run uf
```

## Teletreball (SOCKS5 per SSH)

El servidor nomes es accessible des de la xarxa de la UV. Si treballes de casa
sense VPN, pots fer un tunel SOCKS5 a una maquina de la UV i passar-hi l'app
(usa les variables de proxy estandard, no cal configurar res):

```bash
# Terminal 1: tunel SOCKS contra un host de la uni
ssh -D 1080 -N el_teu_usuari@maquina.uv.es

# Terminal 2: l'app a traves del tunel
ALL_PROXY=socks5h://localhost:1080 teluv f 0612345678
```

Usa `socks5h` (amb la `h`) perque el DNS es resolga a l'altre extrem. El
certificat TLS segueix sent valid perque et connectes al hostname real.
Necessites un host SSH dins la UV amb acces a `pubburjs1.tel.uv.es:443`.

## Opcions principals

- `--base-url`: URL base (per defecte https://pubburjs1.tel.uv.es)
- `--extension-id`: forca una extensio concreta (per defecte es descobreix sola)
- `--timeout`: timeout HTTP
- `--json`: mostra tambe el JSON cru
- `--dry-run`: mostra la peticio i no envia res

## Activar autocompletat (argcomplete)

Per a Bash, activacio global:

```bash
activate-global-python-argcomplete --user
```

Si no vols activacio global, afegix una completio dedicada al teu `~/.bashrc`:

```bash
eval "$(register-python-argcomplete teluv)"
```

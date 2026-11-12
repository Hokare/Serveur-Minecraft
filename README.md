# MC Panel

Interface web pour gérer, sous Linux, des serveurs **itzg/minecraft-server** derrière **itzg/mc-router**, avec suivi des performances.

- Créer / démarrer / arrêter / redémarrer / supprimer des serveurs Minecraft (conteneurs Docker)
- Modifier leurs paramètres (type, version, difficulté, MOTD, mémoire, CPU, hostname, variables personnalisées…)
- Console : journal en direct + commandes RCON
- Performances en direct : CPU, RAM, réseau, joueurs, latence (historique 30 min), ressources de l'hôte
- Routeur mc-router : création, routes découvertes automatiquement, journal, routes manuelles
- Docker : version, images, téléchargement/mise à jour des images

## Installation

Prérequis : Linux avec Docker (et le plugin Compose).

```bash
git clone https://github.com/Hokare/Serveur-Minecraft.git && cd Serveur-Minecraft
docker compose up -d --build
docker logs mc-panel          # affiche le mot de passe initial généré
```

Ouvre <http://127.0.0.1:8080> (utilisateur `admin`). Pour choisir toi-même le mot de passe initial,
mets `PANEL_PASSWORD=...` (et éventuellement `PANEL_USER=...`) dans un fichier `.env` avant le premier lancement.

> Le panel est construit **depuis GitHub** (`main`) : le code doit donc être poussé sur le dépôt.
> Pour construire depuis le dossier local, mets `PANEL_BUILD_CONTEXT=.` dans `.env`.

## Sauvegardes et changements risqués

- Onglet **Sauvegardes** d'un serveur : créer, télécharger, restaurer, supprimer. Une sauvegarde est une archive `.tar.gz`
  du dossier de données (sans `logs`, `cache`, `crash-reports`), stockée dans le volume du panel (`/data/backups/<serveur>/`).
  Le serveur peut rester allumé : le panel suspend l'écriture du monde (`save-off` / `save-all flush`) pendant l'archivage.
- **Restaurer** remplace tout le contenu du serveur par la sauvegarde ; une sauvegarde « avant restauration » est créée d'abord,
  et l'archive est testée avant d'effacer quoi que ce soit.
- Modifier le **type** ou la **version** d'un serveur existant affiche un avertissement et propose une sauvegarde automatique
  avant d'appliquer (baisser la version est signalé comme risque élevé).
- Les sauvegardes sont sur le **même disque** que les serveurs : télécharge les importantes.

## Explorateur de fichiers

Icône **Fichiers** du rail : la liste des serveurs (ordre alphabétique) s'affiche sur le côté ; un clic ouvre le dossier `/data`
du serveur. Tu peux naviguer, ouvrir et modifier les fichiers texte (1 Mo max, Ctrl+S pour enregistrer), créer fichiers et dossiers,
envoyer des fichiers (bouton ou glisser-déposer), télécharger, renommer et supprimer. Ça marche serveur allumé ou arrêté.
Attention : `server.properties` est régénéré au démarrage depuis les paramètres du serveur, et un fichier supprimé ne se récupère pas
(fais une sauvegarde avant les gros changements).

## Mods et plugins

Onglet **Mods / Plugins** : envoi de fichiers `.jar` (128 Mo max, variable `PANEL_MAX_UPLOAD_MB`), liste et suppression.
Le dossier est `plugins/` pour Paper/Purpur/Spigot/Folia, `mods/` pour Fabric/Forge/NeoForge/Quilt. Redémarre ensuite le serveur.

## Profil : compte et mise à jour

Clique sur le cercle **MC** en bas à gauche :

- **Compte** : change le nom d'utilisateur et/ou le mot de passe (le mot de passe actuel est demandé).
  Ils sont stockés hachés dans le volume `mc-panel-data`. Après le changement, le navigateur te redemande de te connecter.
  Si tu perds le mot de passe : `docker compose down -v` n'est **pas** nécessaire, supprime juste `auth.json` :
  `docker exec mc-panel rm /data/auth.json && docker restart mc-panel` (un nouveau mot de passe est généré dans les logs).
- **Logiciel** : compare la version installée au dernier commit GitHub. « Mettre à jour » lance un conteneur
  temporaire `mc-panel-updater` qui reconstruit le panel puis le recrée ; la page se recharge toute seule.
  Tes serveurs Minecraft et le routeur ne sont pas touchés.
  La mise à jour automatique n'est disponible que si le panel a été lancé avec le `docker-compose.yml` fourni.

Sans Docker, pour développer :

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PANEL_PASSWORD=dev python -m app        # http://127.0.0.1:8080 (données dans ./data)
```

## Fonctionnement

- Les serveurs sont des conteneurs `mc-<nom>` sur le réseau Docker `mc-net`, avec un volume `mc-data-<nom>` monté sur `/data`.
- La configuration d'un serveur est stockée dans un label du conteneur : pas de base de données.
- **Modifier un paramètre** recrée le conteneur à l'identique (le monde est conservé) et le redémarre s'il tournait : Docker ne permet pas de changer l'environnement à chaud. Si la recréation échoue, l'ancien conteneur est restauré.
- **mc-router** découvre les serveurs via les labels `mc-router.host` (champ « Hostname(s) » d'un serveur) grâce au socket Docker. Les joueurs se connectent tous sur le port 25565 avec le hostname voulu, ex. `survie.exemple.com`.
- Les joueurs et la latence viennent d'un ping Minecraft (Server List Ping) ; CPU/RAM/réseau viennent de l'API stats de Docker.
- **EULA** : un serveur n'est créé que si tu acceptes l'[EULA de Minecraft](https://www.minecraft.net/en-us/eula).

## Sécurité

Le panel pilote Docker : y accéder équivaut à être root sur la machine.

- L'authentification (HTTP Basic) est toujours active : sans `PANEL_PASSWORD`, un mot de passe aléatoire est généré au premier démarrage.
- Le port est publié sur `127.0.0.1` uniquement. Pour un accès distant, place-le derrière un reverse proxy **HTTPS** (Caddy, Traefik, nginx) ou un tunnel SSH : `ssh -L 8080:127.0.0.1:8080 serveur`.
- Les requêtes d'écriture exigent l'en-tête `X-Requested-With` (anti-CSRF).
- Redirige le port 25565 (routeur) sur ta box, jamais le port 8080.

## Tests

```bash
pip install pytest httpx && python -m pytest tests
```

## Limites connues / pistes

- Le TPS/MSPT n'est pas mesuré (dépend du type de serveur, ex. `/tps` sur Paper).
- Pas encore d'explorateur de fichiers (server.properties, plugins, sauvegardes) ni de sauvegardes planifiées.
- mc-router peut aussi démarrer/arrêter automatiquement les serveurs selon les connexions (auto-scale) : non exposé pour l'instant.
- Le fonctionnement avec un vrai démon Docker n'a pas pu être testé de bout en bout pendant le développement (poste Windows sans Docker actif) : seules la logique (tests unitaires) et l'interface (backend simulé) ont été vérifiées. Fais un premier essai sur une machine Linux avec un serveur de test.

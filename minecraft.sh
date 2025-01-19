#!/bin/bash

boucle="1"
clear

# Récupérer dynamiquement les versions depuis l'API et les trier en ordre décroissant
versions=$(curl -s https://api.papermc.io/v2/projects/paper/ | grep -o '"versions":\[.*\]' | grep -o '"[0-9]\+\.[0-9]\+\(\.[0-9]\+\)\?"' | tr -d '"' | sort -rV)

# Vérifier si la récupération des versions a échoué
if [ -z "$versions" ]; then
    whiptail --title "Erreur" --msgbox "Impossible de récupérer les versions PaperMC." 10 60
    exit 1
fi

# Construire les options pour le menu des versions
menu_options=()
index=1
for version in $versions; do
    menu_options+=("$index" "$version")
    index=$((index + 1))
done

# Ajouter une option pour quitter
menu_options+=("0" "Quitter")

group_name="minecraft"

ops="[
  {
    \"uuid\": \"9711e068-0cb5-4faa-9f7d-58b656b5e277\",
    \"name\": \"Hokare\",
    \"level\": 4,
    \"bypassesPlayerLimit\": false
  }
]"

# Boucle principale
while [ "$boucle" = "1" ]; do
    choix=$(whiptail --title "PaperMC - Choix de la version" --menu "Choisissez une version :" 20 60 12 "${menu_options[@]}" 3>&1 1>&2 2>&3)
    if [ -z "$choix" ] || [ "$choix" = "0" ]; then
        boucle="0"
    else
        selected_version=$(echo "$versions" | sed -n "${choix}p")

        # Récupérer les builds pour la version choisie
        builds=$(curl -s "https://api.papermc.io/v2/projects/paper/versions/$selected_version" | grep -o '"builds":\[.*\]' | grep -o '[0-9]\+' | sort -rV)

        # Vérifier si les builds sont disponibles
        if [ -z "$builds" ]; then
            whiptail --title "Erreur" --msgbox "Aucun build trouvé pour la version $selected_version." 10 60
            continue
        fi

        # Construire les options pour le menu des builds
        build_options=()
        build_index=1
        for build in $builds; do
            build_options+=("$build_index" "Build $build")
            build_index=$((build_index + 1))
        done

        # Ajouter une option pour revenir au menu principal
        build_options+=("0" "Retour")

        # Menu des builds
        boucle_build="1"
        while [ "$boucle_build" = "1" ]; do
            build_choix=$(whiptail --title "PaperMC - Choix du Build" --menu "Version $selected_version - Choisissez un build :" 20 60 12 "${build_options[@]}" 3>&1 1>&2 2>&3)

            if [ -z "$build_choix" ] || [ "$build_choix" = "0" ]; then
                boucle_build="0"
            else
                selected_build=$(echo "$builds" | sed -n "${build_choix}p")
                boucle_name="1"
                name_server=""

                while [ "$boucle_name" = "1" ]; do
                    # Demander le nom du serveur
                    name_server=$(whiptail --title "Nom du serveur" --inputbox "Entrez un nom pour votre serveur :" 10 60 "$name_server" 3>&1 1>&2 2>&3)

                    if [ $? -ne 0 ]; then
                        boucle_name="0" # Quitter la boucle de saisie du nom
                    elif [ -z "$name_server" ]; then
                        whiptail --title "Erreur" --msgbox "Aucun nom de serveur spécifié. Réessayez." 10 60
                    elif [ -d "/minecraft/$name_server" ]; then
                        whiptail --title "Erreur" --msgbox "Le nom du serveur est déjà utilisé. Réessayez." 10 60
                    else
                        # Confirmation et options
                        start_install=$(whiptail --title "Démarrage" --yesno "Le serveur doit démarrer à la fin de l'installation ?" 10 60 --yes-button "OUI" --no-button "NON" 3>&1 1>&2 2>&3; echo $?)
                        auto_start=$(whiptail --title "Auto-démarrage" --yesno "Le serveur doit démarrer automatiquement au démarrage du système ?" 10 60 --yes-button "OUI" --no-button "NON" 3>&1 1>&2 2>&3; echo $?)

                        # Confirmation finale
                        if whiptail --title "Confirmation" --yesno "Version : $selected_version\nBuild : $selected_build\nNom du serveur : $name_server\n\nDémarrage immédiat : $([ "$start_install" -eq 0 ] && echo "OUI" || echo "NON")\nAuto-démarrage : $([ "$auto_start" -eq 0 ] && echo "OUI" || echo "NON")\n\nConfirmez-vous l'installation ?" 15 60; then
                            # Procéder à l'installation
                            mkdir -p "/minecraft/$name_server"
                            if ! getent group "$group_name" > /dev/null; then groupadd "$group_name"; fi
                            chgrp "$group_name" /minecraft

                            if ! command -v screen &> /dev/null; then
                                apt install screen
                            fi

                            # Télécharger le fichier
                            download=$(curl -s "https://api.papermc.io/v2/projects/paper/versions/$selected_version/builds/$selected_build" | grep -o '"downloads":[^}]*' | grep -o 'paper-.*.jar')
                            wget -q -P "/minecraft/$name_server" "https://api.papermc.io/v2/projects/paper/versions/$selected_version/builds/$selected_build/downloads/$download" | whiptail --gauge "Téléchargement de PaperMC..." 10 60 0 || {
                                whiptail --title "Erreur" --msgbox "Le téléchargement a échoué." 10 60
                                continue
                            }
                            mv /minecraft/$name_server/$download /minecraft/$name_server/server.jar #Renommer le fichier jar

                            lanceur="#!/bin/bash
screen -S $name_server java -Xmx6144M -Xms6144M -jar server.jar nogui"

                            echo "eula=true" > /minecraft/$name_server/eula.txt
                            echo "$ops" >> /minecraft/$name_server/ops.json
                            echo "$lanceur" > /minecraft/$name_server/start.sh
                            chmod +x /minecraft/$name_server/start.sh

                            systemed="[Unit]
Description=Minecraft Server $name_server
After=network.target

[Service]
WorkingDirectory=/minecraft/$name_server/
ExecStart=/minecraft/$name_server/start.sh
Restart=always
PermissionsStartOnly=true

[Install].
WantedBy=multi-user.target"

                            echo "$systemed" > /etc/systemd/system/mc$name_server.service

                            systemctl daemon-reload
                            if [ "$auto_start" -eq 0 ]; then systemctl enable mc$name_server.service; fi
                            if [ "$start_install" -eq 0 ]; then systemctl start mc$name_server.service; fi
                            chmod -R 777 /minecraft/

                            whiptail --title "Installation terminée" --msgbox "Le serveur a été installé avec succès dans : /minecraft/$name_server" 10 60

                            boucle_name="0"
                            boucle_build="0"
                            boucle="0"
                        else
                            # Retour à la saisie du nom
                            continue
                        fi
                    fi
                done
            fi
        done
    fi
done
clear
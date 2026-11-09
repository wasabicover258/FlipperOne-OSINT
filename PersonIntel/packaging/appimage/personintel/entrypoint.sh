#! /bin/bash
# Startet die Oberflaeche aus der gebuendelten Python-Laufzeit.
# "-s" haelt Nutzer-site-packages des Wirtssystems fern, damit das AppImage nicht von
# zufaellig installierten Paketen des Hosts abhaengt. Lokale Werkzeuge (holehe, sherlock ...)
# werden absichtlich weiter ueber PATH des Nutzers gefunden.
{{ python-executable }} -s -m personintel "$@"

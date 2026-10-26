#!/bin/sh
# Install this fixed wrapper only after approving the controller deployment.
set -eu
cd "$HOME/engine-room"
exec /usr/bin/python3 -m engine_room.controller_service rpc --root "$HOME/.local/share/engine-room-controller"

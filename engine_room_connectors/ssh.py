"""Optional existing-model SSH connector; no allocation or machine shutdown authority."""
from engine_room.paths import state_root
from ._ssh_attachment import SSHAttachment


def create_connector():
    return SSHAttachment(state_root())

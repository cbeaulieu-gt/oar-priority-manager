# Test Fixtures

## Synthetic fixtures (created by tests)

Tests use `conftest.py` factory functions (`make_submod_dir`, `make_config_json`)
to create fixture directories in `tmp_path`. No static fixtures are committed here
for the initial implementation.

## Real-world fixtures (to be added during first milestone)

During the first implementation milestone, harvest config.json files from 10+
popular OAR mods on Nexus Mods. Place them here with mod author attribution.
These validate the parser against undocumented fields and non-standard formatting.

See spec §11.1 for details.

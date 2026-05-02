"""Function tools exposed to the agents.

Intentionally empty re-exports: each tool function shares a name with its
module (e.g. `retrieve_incidents`), and re-exporting the function from
the package would shadow the module attribute, breaking
`import rca_system.tools.retrieve_incidents` for tests that monkeypatch
the module-level `_memory` singleton. Consumers should import directly:

    from rca_system.tools.retrieve_incidents import retrieve_incidents
"""

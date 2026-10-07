"""GraphQL types of the Guide (mirrors ``services/read/guide``, ADR 0051): ``GuideIndex`` (the
sections, field theme groups, intents, situations, playbooks by family, regime indicators and
episodes) and ``GuideField`` (a field's page: its ``FeatureInfo``, related fields, the
playbooks that use it and the situations that fool it); each mirrors a read dataclass through
one ``.of()``."""

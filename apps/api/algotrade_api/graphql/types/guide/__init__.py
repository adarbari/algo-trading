"""GraphQL types of the Guide (mirrors ``services/read/guide``, ADR 0051): ``GuideIndex`` (the
sections, field theme groups, intents, situations, playbooks by family, regime indicators,
episodes, Start here pages and glossary terms), ``GuideField`` (a field's page: its
``FeatureInfo``, related fields, the playbooks that use it and the situations that fool it),
``GuidePlaybookDetail`` and ``GuideSituationDetail`` (a playbook's and a situation's page), the
indicator and episode pages, ``GuideTerm`` and ``GuideStartPage`` (the written pages),
``GuideSearch`` (the grouped search results) and ``GuideProse`` (prose split at the catalogue
names it mentions); each mirrors a read dataclass through one ``.of()``."""

# Code Review : composable-agents

## Vue d'ensemble

Framework Python qui transforme des fichiers YAML de configuration d'agents IA en API HTTP/WebSocket via FastAPI. Repose sur `deepagents` (LangGraph) avec support multi-agents, Human-In-The-Loop, MCP servers, et plusieurs providers LLM.

---

## Architecture (9/10)

**Architecture hexagonale rigoureuse** avec séparation stricte en couches :

- **Domain** : entités Pydantic immutables (`frozen=True`), ports abstraits (ABC), hiérarchie d'exceptions typées — zéro dépendance framework
- **Application** : use cases, routes FastAPI (couche fine), modèles de requêtes
- **Infrastructure** : adaptateurs concrets (DeepAgent, YAML, MCP, tracing)

La règle de dépendance est correctement appliquée : le domaine n'importe rien de l'infrastructure. L'inversion de dépendance est propre. Principes SOLID respectés.

## Typage et validation (8/10)

- Pydantic v2 avec `frozen=True` pour l'immutabilité
- Validators custom (`@model_validator`) pour contraintes complexes
- Enums typées (`StrEnum`) pour middleware, backend, rôles
- **Faiblesses** : `Thread.messages: list` au lieu de `list[Message]`, paramètre `message` non typé dans `ThreadRepository.add_message()`

## Tests (7/10)

- 27 fichiers de tests unitaires
- Test doubles bien conçus (fakes, pas mocks) pour chaque port
- Injection de dépendances pour les tests via `override_dependencies()`
- **Faiblesses** : pas de métriques de couverture, couverture WebSocket limitée

## Documentation (9/10)

- README complet (~28K caractères) : quickstart, architecture, API reference, exemples curl
- CONTRIBUTING.md détaillé avec principes d'architecture
- Docstrings sur les méthodes publiques
- Exemples YAML variés (minimal, research, code-review, MCP)

## Sécurité (6/10)

- `yaml.safe_load()` utilisé correctement
- API keys via variables d'environnement, `.env` dans `.gitignore`
- **Risques** : chargement dynamique de modules via `importlib.import_module()` depuis YAML, pas de validation headers MCP, pas d'authentification, pas de rate limiting

## Production-readiness (4/10)

| Manque | Impact |
|--------|--------|
| Persistence (in-memory uniquement) | Données perdues au redémarrage |
| Authentification/autorisation | API exposée sans protection |
| Logging structuré | Pas de traçabilité des opérations |
| Rate limiting | Vulnérable aux abus |
| Pagination | Scalabilité des endpoints de liste |
| Nettoyage MCP | `close()` contient un `pass` TODO |

---

## Utilité

| Critère | Evaluation |
|---------|-----------|
| Problème résolu | Réel : déployer des agents configurables sans code |
| Différenciation | Faible : LangServe, CrewAI, AutoGen sont plus matures |
| Production | Non prêt |
| Prototypage | Oui, très adapté pour des PoC |
| Extensibilité | Excellente grâce à l'architecture hexagonale |
| Maintenabilité | Bonne : code propre, bien structuré, testé |

## Recommandations prioritaires

1. Ajouter un adaptateur de persistence (SQLite/PostgreSQL)
2. Implémenter un middleware d'authentification
3. Ajouter du logging structuré (`structlog`)
4. Compléter le nettoyage MCP (`close()`)
5. Unifier la langue du code en anglais
6. Ajouter métriques et rate limiting
7. Configurer des pre-commit hooks

## Score global : 7.5/10

Projet bien architecturé avec une excellente maîtrise des principes de conception. Idéal pour le prototypage, mais nécessite des améliorations significatives pour un usage en production.

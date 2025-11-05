# Changelog

## [0.1.4] - 2025-10-03

### Fixed
- Critical bug: HTTP POST responses now properly parsed
- Version negotiation now parses server's supported versions from error data
- Transport detection timeout increased from 0.2s to 0.5s for better reliability
- Resource cleanup now resets _http_post_mode on failure
- CLI printing logic now properly handles content and result variables

### Improved
- POST-SSE path now uses proper streaming AsyncClient.stream()
- Response parsing uses consistent json.loads() in streaming contexts
- Transport detection propagates selected transport to MCPModule
- Pydantic model generation now handles enums and arrays properly
- Security URL validation allows localhost when --transport is explicitly set
- Accept headers now included on all requests for better server compatibility
- CLI now passes transport parameter to fetch_schema for proper detection
- Security validation uses ipaddress module for robust private IP detection
- Version management uses single source of truth in __init__.py

### Added
- Unit tests for POST-SSE functionality with proper mocking
- Verbose logging for transport and protocol version selection
- __all__ exports in top-level package for clean public API
- CLI --timeout flag to override all timeout settings
- Proper typing imports with typing-extensions support
- httpx>=0.27 version pin for API stability
- Pydantic v2 mypy plugin support
- TODO comments for complex array item types in codegen

# Changelog

All notable changes to the Bylaws-IQ project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2025-09-02] - Complete System Documentation

### System Overview for New Developers

This entry serves as a comprehensive document for developers. The system is a sophisticated AI-powered zoning analysis platform that automatically discovers, analyzes, and extracts zoning metrics from official municipal documents.

#### **Core Mission & Value Proposition**
The application solves a critical problem in real estate and development: quickly obtaining accurate, verifiable zoning information for any Massachusetts address. Instead of manually searching through municipal websites and analyzing complex zoning documents, users simply enter an address and receive comprehensive zoning metrics with official source citations.

#### **Complete End-to-End Workflow**

1. **Address Input** → User enters any Massachusetts address
2. **Geocoding** → System determines precise location and jurisdiction using Mapbox/Geoapify
3. **Official Website Discovery** → Finds the authoritative municipal website via MMA database
4. **Zoning Map Discovery** → Locates and analyzes official zoning maps using AI
5. **Zoning District Identification** → Determines specific zoning district for the address
6. **Bylaws Document Discovery** → Finds official zoning bylaws PDFs using multi-method approach
7. **AI-Powered Analysis** → Extracts specific metrics using Google Gemini 2.5 Pro
8. **Results & Citations** → Presents findings with verifiable source links

### Added - Complete Feature Set

#### **1. Modular Agent Architecture**
- **BaseZoningAgent**: Shared infrastructure for WebDriver management, LLM integration, MMA lookups
- **ZoningMapAgent**: Specialized for discovering and analyzing zoning maps to determine districts
- **ZoningBylawsAgent**: Expert at finding official zoning bylaws using sophisticated search methods
- **CombinedZoningAgent**: Orchestration layer that coordinates all agents seamlessly

#### **2. Sophisticated Zoning Map Discovery System**
- **Official Website Detection**: Uses Massachusetts Municipal Association database for authentic .gov sites
- **Dynamic Search Navigation**: Selenium WebDriver automates municipal website searches
- **AI-Powered Map Selection**: Gemini Flash 1.5 evaluates and selects most recent zoning maps from search results
- **Direct PDF Analysis**: Gemini 2.5 Pro analyzes zoning maps directly from URLs without downloading
- **District Extraction**: Identifies specific zoning codes (e.g., "R-1", "B-2") and overlay districts
- **Fallback Systems**: Multiple strategies when primary search methods encounter obstacles

#### **3. Advanced Zoning Bylaws Discovery Engine**
**Multi-Method Discovery Strategy:**
- **Method 1**: "Zoning Board of Appeals" page search with exact/partial matching logic
- **Method 2**: "Planning Board" page search as comprehensive fallback
- **Early Termination**: Stops immediately upon finding valid documents to optimize performance

**4-Tier Document Detection System:**
- **Tier 1**: Direct text element scanning with parent link detection
- **Tier 2**: Comprehensive scanning of buttons, divs, spans for clickable elements
- **Tier 3**: Element attribute keyword matching (alt, title, aria-label, value)
- **Tier 4**: Deep DOM traversal with JavaScript extraction and clickable parent detection

**Priority-Based Document Processing:**
- **Priority 1**: PDF documents (immediate download and analysis)
- **Priority 2**: Ecode360 links (specialized processing with anti-bot measures)
- **Priority 3**: Nested page links (recursive document search)

#### **4. Ecode360 Integration Engine**
**Fresh WebDriver Methodology:**
- Creates dedicated Chrome instances specifically for ecode360.com processing
- Advanced anti-bot bypass: realistic user agents, session establishment, human-like navigation
- CAPTCHA detection and automatic session refresh capabilities
- Multiple Chrome initialization strategies (ChromeDriverManager, system paths, default detection)

**Sophisticated Document Access:**
- 15+ CSS selectors for robust "Download" button detection across different page layouts
- XPath fallback system for text-based element searching when selectors fail
- Chrome DevTools Protocol integration for direct PDF generation using `Page.printToPDF`
- Intelligent file naming: `{District}_Zoning_ecode.pdf` with organized storage in `pdf_downloads/`

#### **5. Large Language Model Integration**
**Multi-Model Architecture:**
- **Google Gemini 2.5 Pro**: Complex document analysis, zoning metric extraction, district identification
- **Google Gemini Flash 1.5**: Document selection, website classification, PDF ranking tasks
- **OpenRouter API**: Unified access to both models with structured JSON output enforcement
- **Context Management**: Intelligent content truncation and token allocation based on task complexity

**Structured Output System:**
- JSON schema enforcement using OpenRouter's `response_format` feature
- Automatic validation and error recovery for malformed responses
- Comprehensive prompt engineering for consistent, accurate results

#### **6. Manual Zoning District Fallback System**
**Resource-Preserving Fallback:**
- Detects when automated zoning map discovery fails to determine district
- Preserves all discovered resources (official website, agent instances) from initial discovery
- User-friendly form interface with two validated input fields:
  - Zoning District Name (e.g., "Business District", "Mixed Use Industrial")
  - Zoning District Code (e.g., "B-1", "I-3", "R-2")
- Seamless pipeline continuation without resource waste or redundant lookups
- Complete workflow reset option with "Cancel Research" functionality

#### **7. Comprehensive Error Handling & Fallback Systems**
**User-Controlled Fallbacks:**
- Primary method failure detection with transparent user communication
- User consent system for fallback methods with clear options
- Complete process visibility and method success/failure reporting

**Technical Error Recovery:**
- **PDF Access Issues**: 5-strategy approach for 403 Forbidden errors including browser simulation, government website patterns, mobile user-agents
- **WebDriver Resilience**: Multiple Chrome initialization methods for different environments
- **LLM Error Handling**: Comprehensive JSON parsing with markdown wrapper removal
- **Network Resilience**: Retry logic, timeout handling, and graceful degradation

#### **8. Professional Web Interface**
**Streamlit-Based UI:**
- Clean, intuitive interface for address input and results display
- Real-time progress updates with agent-specific status messages
- Session state management for complex workflows and fallback handling
- Responsive design with proper error messaging and user guidance

**Result Presentation:**
- Comprehensive metric display with confidence scores
- Direct links to source documents for verification
- Zoning district information with codes, names, and overlays
- Professional JSON export functionality for integration with other systems

#### **9. Robust Testing Infrastructure**
**Individual Agent Testing:**
- `test_zoning_map_agent.py`: Isolated testing for zoning map discovery
- `test_zoning_bylaws_agent.py`: Comprehensive bylaws discovery testing
- Configurable test addresses with detailed logging and error reporting
- Method-specific testing capabilities for debugging individual strategies

#### **10. Advanced Document Processing Pipeline**
**Multi-Format Support:**
- Regular PDFs with PyPDF2 text extraction
- Ecode360 PDFs from generated files
- Ecode360 HTML with BeautifulSoup text extraction
- Content validation and character count verification

**Deduplication System:**
- Prevents re-downloading identical PDFs found on multiple pages
- Source tracking for comprehensive audit trails
- Memory-efficient processing with dictionary-based tracking

### Technical Implementation Details

#### **Dependencies & Infrastructure**
- **Web Automation**: Selenium WebDriver with Chrome, webdriver-manager for cross-platform compatibility
- **HTTP Handling**: httpx and requests with advanced retry logic and anti-bot strategies
- **PDF Processing**: PyPDF2 for text extraction, Chrome DevTools Protocol for PDF generation
- **HTML Processing**: BeautifulSoup4 for DOM manipulation and content extraction
- **AI Integration**: OpenRouter API for Google Gemini model access with structured outputs
- **UI Framework**: Streamlit for web interface with session management
- **Geocoding**: Multi-provider support (Mapbox, Geoapify, Nominatim) with failover

#### **Data Storage & Organization**
- **PDF Downloads**: Organized storage in `pdf_downloads/` with intelligent naming conventions
- **Session Management**: Streamlit session state for UI persistence and workflow continuity
- **Logging System**: Comprehensive structured logging with performance metrics and debugging information

#### **Security & Reliability**
- **Environment Variables**: Secure API key management through .env files
- **Anti-Bot Measures**: Sophisticated strategies to avoid detection and blocking
- **Resource Management**: Proper WebDriver cleanup and memory management
- **Error Boundaries**: Comprehensive exception handling with graceful degradation

### Current Capabilities & Limitations

#### **What the System Can Do:**
- Analyze any Massachusetts address for zoning information
- Discover official municipal websites automatically
- Navigate complex municipal websites with dynamic content
- Find and analyze zoning maps using AI
- Locate official zoning bylaws through multiple search strategies
- Handle ecode360.com hosted documents with anti-bot measures
- Extract specific zoning metrics (setbacks, lot coverage, height limits, parking requirements)
- Provide verifiable citations to official sources
- Handle user fallback input when automation fails
- Process multiple document formats (PDF, HTML, ecode360)
- Generate confidence scores for extracted information

#### **Known Limitations:**
- **Geographic Scope**: Currently focused on Massachusetts municipalities
- **Document Dependencies**: Relies on municipal websites having searchable content
- **Model Context**: Limited by Gemini model token limits (32K tokens)
- **Website Variations**: Some municipal sites may use unsupported structures
- **Internet Dependency**: Requires reliable internet connection for all operations

#### **Performance Characteristics:**
- **Typical Processing Time**: 30-60 seconds for complete analysis
- **Success Rate**: High success rate for major Massachusetts municipalities
- **Resource Usage**: Moderate CPU and memory usage due to WebDriver operations
- **Scalability**: Single-user focused, not designed for high-concurrency workloads

### Development Environment Setup

#### **Required Environment Variables:**
```bash
OPENROUTER_API_KEY=your_openrouter_key    # Google Gemini model access
TAVILY_API_KEY=your_tavily_key            # Fallback search integration  
MAPBOX_TOKEN=your_mapbox_token            # Primary geocoding service
```

#### **Installation & Launch:**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Configure with your API keys
streamlit run app/main.py
```

### Debugging & Troubleshooting

#### **Logging System:**
- **Agent-Level Tracking**: Individual logging for each specialized agent
- **Performance Metrics**: Step-by-step timing with span-based measurement
- **Debug Information**: Detailed process flow and decision point logging
- **Error Tracking**: Full exception handling with stack traces

#### **Common Issues & Solutions:**
- **WebDriver Issues**: Multiple initialization strategies handle different environments
- **PDF Access Problems**: 5-strategy approach handles most access restrictions
- **LLM Response Issues**: Comprehensive JSON parsing with error recovery
- **Municipal Website Changes**: Multi-method approach provides resilience

### Future Development Considerations

#### **Extensibility Points:**
- **Geographic Expansion**: Framework ready for other states with agent specialization
- **New Document Types**: Extensible processing pipeline for additional formats
- **Additional Metrics**: Easy addition of new zoning metrics to extraction system
- **API Integration**: Streamlined addition of new LLM providers or search services

#### **Maintenance Requirements:**
- **Regular Testing**: Periodic testing with real addresses to ensure functionality
- **Dependency Updates**: Keep WebDriver and browser versions synchronized
- **API Key Management**: Monitor usage limits for OpenRouter and other services
- **Municipal Website Changes**: May require periodic updates to navigation strategies

This system represents a sophisticated integration of web automation, artificial intelligence, and document processing technologies to solve a real-world problem in the real estate and development sectors. The modular architecture and comprehensive error handling make it both powerful and maintainable.

## [Unreleased]

### Added
- Manual Zoning District Fallback System
  - User-friendly form interface when automated zoning map discovery fails
  - Two input fields for zoning district name and code with validation
  - Resource preservation system to maintain discovered official website
  - Seamless pipeline continuation without resource waste
  - Cancel Research functionality to reset workflow
- Resource preservation between ZoningMapAgent and ZoningBylawsAgent
- Enhanced error handling for zoning map discovery failures
- Dedicated testing scripts for individual agent components

### Changed
- Enhanced `run_query_with_manual_zoning()` function to accept preserved resources
- Modified UI to pass preserved official website and agent instances
- Updated pipeline to detect and handle zoning map discovery failures
- Improved session state management for manual zoning district input

### Fixed
- Resource waste when ZoningMapAgent discovers official website but fails on district identification
- Redundant MMA lookups when ZoningBylawsAgent is called after map discovery failure
- Agent instance recreation causing loss of discovered website information

## [Previous Releases]

### Added in Previous Development Sessions
- Modular agent architecture with BaseZoningAgent, ZoningMapAgent, and ZoningBylawsAgent
- Comprehensive zoning map discovery and analysis system
- Multi-method zoning bylaws discovery (Zoning Board of Appeals + Planning Board)
- Enhanced Ecode360 integration with advanced anti-bot bypass
- Fresh WebDriver methodology for optimal processing
- 4-tier element detection system with comprehensive DOM scanning
- Priority-based document processing (PDF → ecode360 → nested pages)
- Advanced deduplication system for preventing redundant downloads
- Google Gemini 2.5 Pro and Gemini Flash 1.5 integration via OpenRouter
- Structured JSON output enforcement for LLM responses
- User-controlled fallback system with consent mechanisms
- Comprehensive error recovery for PDF access issues
- Massachusetts Municipal Association (MMA) database integration
- Dynamic content navigation with Selenium WebDriver
- Multi-provider geocoding services (Mapbox, Geoapify, Nominatim)
- Streamlit web interface with session management
- Structured logging system with performance metrics

---

## How to Use This Changelog

### For Each Coding Session:

1. **Before starting**: Note the current date and what you plan to work on
2. **During development**: Keep track of changes as you make them
3. **After completing work**: Document your changes in the appropriate section below

### Change Categories:

- **Added**: New features, functionality, or files
- **Changed**: Changes to existing functionality, refactoring, improvements
- **Deprecated**: Soon-to-be removed features (mark for future removal)
- **Removed**: Removed features, deleted files, cleaned up code
- **Fixed**: Bug fixes, error corrections, issue resolutions
- **Security**: Security-related improvements or fixes

### Entry Format:

```markdown
## [Version/Date] - YYYY-MM-DD

### Added
- Brief description of new feature or functionality
- Another new feature with specific details

### Changed  
- Description of what was modified and why
- Refactoring or improvements made

### Fixed
- Bug fix description with context
- Error resolution details

### Removed
- What was deleted and why
- Cleanup activities
```

### Example Entry:

```markdown
## [2025-01-15] - Manual Zoning District Implementation

### Added
- Manual zoning district input form with validation
- Resource preservation system for agent instances
- Cancel Research workflow reset functionality

### Changed
- Enhanced run_query_with_manual_zoning to accept preserved resources
- Modified UI to pass discovered websites between agents

### Fixed
- Resource waste when ZoningMapAgent fails after website discovery
- Redundant MMA lookups in ZoningBylawsAgent
```

---

## Template for New Entries

Copy and fill out this template for each coding session:

```markdown
## [YYYY-MM-DD] - Session Description

### Added
- 

### Changed
- 

### Fixed
- 

### Removed
- 

### Notes
- 

```

---

## Development Guidelines

### Version Numbering
- **Major** (X.0.0): Breaking changes, major feature additions
- **Minor** (0.X.0): New features, significant improvements  
- **Patch** (0.0.X): Bug fixes, small improvements

### Commit Message Reference
When documenting changes, you can reference specific commits if helpful:
- `Added manual zoning district fallback (commit: abc1234)`
- `Fixed agent resource preservation (commit: def5678)`

### Testing Notes
Include testing information when relevant:
- Manual testing completed for manual zoning district flow
- Unit tests added for resource preservation
- Integration testing with real addresses

---

## Maintenance Notes

### Regular Cleanup
- Review and consolidate entries quarterly
- Move older entries to archived sections
- Update version numbers for releases

### Documentation Sync
- Update README.md when major features are added
- Sync technical specifications with actual implementation
- Keep dependency lists current


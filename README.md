# Bylaws-IQ: Advanced Zoning Bylaws Analysis System

Bylaws-IQ is a sophisticated automated system that discovers, analyzes, and extracts specific zoning metrics for any address in Massachusetts. The system combines advanced web automation, official document discovery, and large language model analysis to provide accurate zoning information with verifiable citations.

## Overview

Bylaws-IQ combines multiple advanced technologies in a sophisticated modular architecture to deliver a complete zoning analysis workflow:

### Key Features
- **Modular Agent Architecture**: Specialized agents for zoning maps and bylaws with shared infrastructure
- **Official Website Discovery**: Uses Massachusetts Municipal Association (MMA) database for authoritative municipal websites
- **Dynamic Content Navigation**: Selenium-powered web automation for complex municipal website interactions  
- **Multi-Method Document Discovery**: Battle-tested bylaws PDF discovery using multiple search strategies with early termination
- **Enhanced Ecode360 Integration**: Advanced anti-bot bypass strategies and Chrome DevTools Protocol PDF generation  
- **Large Language Model Analysis**: Google Gemini 2.5 Pro and Gemini Flash 1.5 via OpenRouter for document analysis and intelligent selection
- **Comprehensive Error Handling**: Robust fallback mechanisms with user consent controls and resource optimization

### Technical Highlights
- **4-Tier Element Detection**: Comprehensive DOM scanning with JavaScript extraction and clickable parent detection
- **5-Strategy Search Interaction**: Handles overlays, dynamic content, and complex website interactions
- **Fresh WebDriver Sessions**: Dedicated Chrome instances for optimal ecode360.com processing
- **Website Reuse Optimization**: Efficient caching and sharing of discovered official websites between agents
- **Priority-Based Processing**: Intelligent document type prioritization (PDF → ecode360 → nested pages)
- **Advanced Deduplication**: Prevents redundant downloads while tracking all discovery sources

## System Architecture

### Core Pipeline Flow

1. **Address Geocoding** → 2. **Zoning Map Discovery & Analysis** → 3. **Zoning Bylaws Discovery & Processing** → 4. **AI-Powered Metric Synthesis** → 5. **Results & Citations**

### Modular Agent Architecture

The system employs a sophisticated modular architecture with specialized agents for different aspects of zoning analysis:

#### **BaseZoningAgent** - Shared Infrastructure
- **WebDriver Management**: Chrome WebDriver initialization with multiple fallback strategies
- **LLM Integration**: OpenRouter API integration with structured JSON outputs
- **MMA Lookup**: Massachusetts Municipal Association database access with robust error handling
- **Domain Normalization**: Consistent website URL handling across all agents
- **PDF Management**: Download, access, and text extraction utilities

#### **ZoningMapAgent** - Map Discovery & District Analysis
- **Official Website Discovery**: MMA database integration with caching for efficiency
- **Dynamic Map Search**: Municipal website search tool utilization
- **LLM-Powered Map Selection**: Model-driven selection of most recent and relevant zoning maps using Gemini Flash 1.5
- **Direct PDF Analysis**: Document analysis of zoning maps from URLs using Gemini 2.5 Pro
- **District Identification**: Extraction of specific zoning district codes and overlay information
- **Website Caching**: Efficient reuse of discovered official websites

#### **ZoningBylawsAgent** - Comprehensive Bylaws Discovery
- **Multi-Method Discovery System**: Sophisticated search strategies for maximum success rate
- **Advanced Document Detection**: 4-tier detection system with comprehensive element scanning  
- **Ecode360 Integration**: Specialized handling for ecode360.com hosted bylaws
- **Fresh WebDriver Sessions**: Clean Chrome sessions for optimal processing
- **Priority-Based Processing**: Intelligent document type prioritization (PDF → ecode360 → pages)
- **Website Reuse**: Leverages cached websites from ZoningMapAgent for efficiency

#### **CombinedZoningAgent** - Orchestration Layer
- **Unified Interface**: Single entry point maintaining backward compatibility
- **Agent Coordination**: Seamless orchestration between map and bylaws agents
- **State Management**: Efficient data sharing between specialized agents
- **Error Handling**: Comprehensive error recovery across all agent operations

### Key Components

#### 1. Address Processing & Geocoding (`bylaws_iq/services/geocode.py`)
- **Multi-Provider Support**: Mapbox, Geoapify, Nominatim fallbacks
- **Jurisdiction Extraction**: Automatically determines city, state, and administrative boundaries
- **Coordinate Precision**: Provides accurate lat/lng for zoning analysis

#### 2. Zoning Map Discovery & Analysis (ZoningMapAgent)
- **Dynamic Search**: Uses municipal website search tools to find "Zoning Map" documents
- **Model-Based Selection**: Gemini Flash 1.5 selects most recent and relevant zoning maps from search results
- **Direct PDF Analysis**: Analyzes zoning maps directly from URLs using Gemini 2.5 Pro
- **District Identification**: Extracts specific zoning district codes and overlay information
- **Website Caching**: Efficient storage and reuse of discovered official websites

#### 3. Multi-Method Bylaws Discovery System (ZoningBylawsAgent)

The system employs a comprehensive, battle-tested multi-method approach for discovering zoning bylaws with sophisticated fallback strategies:

##### **Method 1: Zoning Board of Appeals Search**
- **Search Target**: "Zoning Board of Appeals" pages using municipal website search tools
- **Selection Logic**: Exact match preferred, falls back to first partial match containing full phrase
- **Document Discovery**: Enhanced methodology with fresh WebDriver sessions for optimal processing
- **Priority Processing**: PDF documents → ecode360 links → nested pages

##### **Method 2: Planning Board Search** 
- **Search Target**: "Planning Board" pages as comprehensive fallback method
- **Selection Logic**: Exact match only for precision
- **Same Processing Pipeline**: Uses identical advanced document discovery as Method 1
- **Full Integration**: Complete ecode360 and PDF handling capabilities

##### **Advanced Search Infrastructure**
- **5-Strategy Safe Search Interaction**: Handles complex websites with overlays, JavaScript, and dynamic content
- **Multi-Selector Input Detection**: Comprehensive search input field detection across CMS platforms
- **Robust Submit Handling**: Multiple submission methods (Enter key, button clicks, form submission)
- **Anti-Bot Strategies**: Advanced Chrome options and session management to avoid detection

##### **Comprehensive Document Discovery System**
1. **4-Tier Element Detection**:
   - **Strategy 1**: Direct text element scanning with parent link detection
   - **Strategy 2**: Button/clickable element comprehensive scanning (div, span, button, input)
   - **Strategy 3**: Element attribute keyword matching (alt, title, aria-label, value)
   - **Strategy 4**: Deep DOM traversal with clickable parent detection and JavaScript extraction

2. **Priority-Based Processing**:
   - **Priority 1**: PDF documents (direct download and processing)
   - **Priority 2**: Ecode360 links (fresh WebDriver methodology)
   - **Priority 3**: Nested page links (recursive document search)

3. **Comprehensive Keyword Matching**:
   - "Zoning Code", "Zoning Bylaw", "Zoning By-law", "Zoning Bylaws"
   - "Zoning Ordinance", "Unified Development Ordinance (UDO)", "UDO"
   - "Form-Based Code", "Zoning Regulation", "Zoning Regulations"
   - "Zoning Act", "Zoning Law"

##### **Early Termination & Optimization**
- **Success-Based Termination**: Stops processing immediately after finding valid documents
- **Duplicate Prevention**: Advanced deduplication system tracks downloads across multiple discovery paths
- **Source Attribution**: Records all discovery paths while preventing redundant processing
- **Performance Optimization**: Reduces WebDriver operations, LLM calls, and processing time

#### 4. Enhanced Ecode360 Processing System

Advanced integration for ecode360.com hosted municipal bylaws with comprehensive anti-bot strategies:

##### **Fresh WebDriver Methodology**
- **Clean Session Architecture**: Initializes dedicated Chrome WebDriver instances for optimal ecode360 processing
- **Multi-Path Chrome Initialization**: ChromeDriverManager primary, system Chrome fallbacks with path detection
- **Advanced Anti-Bot Bypass**: Comprehensive Chrome options, session establishment, and human behavior simulation
- **CAPTCHA Detection & Avoidance**: Automatic detection with session refresh and navigation strategies

##### **Sophisticated Document Access**
- **Multi-Selector Download Detection**: 15+ CSS selectors for robust "Download" button detection
- **XPath Fallback System**: Text-based element searching when CSS selectors fail
- **Navigation Strategies**: Smart navigation with session establishment and human-like behavior
- **Content Validation**: Multi-keyword validation ensuring meaningful zoning content extraction

##### **Chrome DevTools Protocol Integration**
- **PDF Generation**: Direct `Page.printToPDF` usage with custom headers and formatting
- **Organized Storage**: Structured naming system (`{District}_Zoning_ecode.pdf`) in `pdf_downloads/`
- **Fallback Systems**: HTML storage as backup when PDF generation fails
- **File Validation**: Size and content verification with detailed logging

##### **Advanced Processing Features**
- **Domain-Based District Extraction**: Intelligent district name parsing from source URLs
- **Content Quality Assessment**: Keyword-based validation (zoning, district, bylaw, ordinance, use, setback, coverage)
- **Session Management**: Proper cleanup and resource management for fresh WebDriver instances
- **Error Recovery**: Comprehensive exception handling with fallback processing methods

#### 5. Document Processing Pipeline (`bylaws_iq/pipeline.py`)

##### **Multi-Format Support**
- **Regular PDFs**: PyPDF2-based text extraction with per-page processing
- **Ecode360 PDFs**: Direct PDF reading from generated files  
- **Ecode360 HTML**: BeautifulSoup text extraction as fallback
- **Content Validation**: Comprehensive logging and character count verification

##### **Deduplication System**
- **PDF Tracking**: Prevents re-downloading identical PDFs found on multiple pages
- **Source Tracking**: Records all discovery paths while avoiding duplicate processing
- **Memory Optimization**: Efficient tracking using dictionary-based deduplication

#### 6. Large Language Model Analysis System (`bylaws_iq/services/llm.py`)

##### **Multi-Model Architecture**
- **Primary Analysis**: Google Gemini 2.5 Pro via OpenRouter for complex document analysis and metric extraction
- **Document Selection**: Google Gemini Flash 1.5 for PDF selection and classification tasks
- **Structured Output**: JSON schema enforcement using OpenRouter's `response_format` feature with strict validation
- **Token Management**: Intelligent content truncation and context allocation based on task complexity

##### **Advanced Document Selection System**
- **Multi-PDF Analysis**: Automated selection of most recent versions when multiple documents found
- **Date Pattern Recognition**: Language model analysis of version dates and document currency using Gemini Flash 1.5
- **Structured Selection Response**: JSON-formatted selection with reasoning and confidence scoring
- **Fallback Processing**: Non-structured JSON prompting when schema enforcement unavailable

##### **Comprehensive Metric Synthesis Process**
- **Context-Aware Analysis**: Incorporates discovered zoning district codes and overlay information
- **District-Specific Extraction**: Targets metrics specifically for the determined zoning district
- **Multi-Category Coverage**: Extracts building height, setbacks, lot coverage, parking, FAR, density, permitted uses using Gemini 2.5 Pro
- **Citation Generation**: Creates traceable citations back to source documents with page references
- **Quality Validation**: Multiple validation layers for JSON output, content completeness, and accuracy

#### 7. Fallback & Error Handling System

##### **User-Controlled Fallbacks**
- **Primary Method Failure Detection**: Monitors official document discovery success
- **User Consent System**: Presents options when primary methods fail
  - **Continue with Fallback**: Uses general search methods if user approves
  - **Stop Processing**: Returns "unable to help" message if user declines
- **Transparent Process**: Full visibility into method success/failure

##### **Robust Error Recovery**
- **PDF Access Issues**: Multiple HTTP request strategies for 403 Forbidden errors
  - Browser simulation with full session establishment
  - Government website navigation patterns
  - Mobile user-agent fallbacks
  - HTTP header optimization
- **WebDriver Resilience**: Multiple Chrome initialization strategies for different environments
- **LLM Error Handling**: Comprehensive JSON parsing with markdown wrapper removal

## Technical Specifications

### Dependencies
- **Web Automation**: Selenium WebDriver with Chrome WebDriver management
- **HTTP Requests**: httpx, requests with advanced retry logic and anti-bot strategies
- **PDF Processing**: PyPDF2 for text extraction, Chrome DevTools Protocol for PDF generation
- **HTML Processing**: BeautifulSoup4 for DOM manipulation and content extraction
- **Language Model Integration**: OpenRouter API for Google Gemini 2.5 Pro and Gemini Flash 1.5
- **Search Integration**: Tavily API for fallback document searches  
- **UI Framework**: Streamlit for web interface and session management

### Model Specifications
- **Primary Analysis Model**: Google Gemini 2.5 Pro
  - **Use Cases**: Complex document analysis, zoning metric extraction, district identification
  - **Context Window**: 32,768 tokens
  - **Structured Output**: JSON schema enforcement via OpenRouter
  - **Temperature**: 0.1 for consistent, factual responses
- **Classification Model**: Google Gemini Flash 1.5  
  - **Use Cases**: Document selection, website classification, PDF ranking
  - **Context Window**: 32,768 tokens
  - **Response Format**: Structured JSON with reasoning
  - **Temperature**: 0.0 for deterministic classification

### Environment Variables Required
```bash
OPENROUTER_API_KEY=your_openrouter_api_key      # Google Gemini model access via OpenRouter
TAVILY_API_KEY=your_tavily_api_key              # Search fallback integration
MAPBOX_TOKEN=your_mapbox_token                  # Primary geocoding service
# OR GEOAPIFY_KEY=your_geoapify_key             # Alternative geocoding service
```

### Data Storage
- **PDF Downloads**: `pdf_downloads/` directory for organized document storage
- **Session State**: Streamlit session management for UI state persistence
- **Logging**: Comprehensive structured logging with performance metrics

## Quick Start

### Installation
```bash
# 1. Clone and setup virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2. Install dependencies  
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env with your API keys
```

### Configuration
Create `.env` file in project root:
```env
OPENROUTER_API_KEY=your_openrouter_key
TAVILY_API_KEY=your_tavily_key  
MAPBOX_TOKEN=your_mapbox_token
```

### Launch Application
```bash
streamlit run app/main.py
```

## Project Structure

```
bylaws_iq/
├── app/
│   └── main.py                      # Streamlit web interface
├── bylaws_iq/
│   ├── __init__.py
│   ├── models.py                    # Pydantic data models and schemas  
│   ├── pipeline.py                  # Main orchestration and workflow logic
│   ├── logging_config.py            # Structured logging configuration
│   └── services/
│       ├── base_zoning_agent.py     # BaseZoningAgent - Shared infrastructure:
│       │                            #   - WebDriver management
│       │                            #   - LLM integration (OpenRouter/Gemini)
│       │                            #   - MMA lookup utilities
│       │                            #   - PDF processing
│       ├── zoning_map_agent.py      # ZoningMapAgent - Map discovery & analysis:
│       │                            #   - Official website discovery
│       │                            #   - Dynamic map search
│       │                            #   - Gemini-based map selection
│       │                            #   - Zoning district identification
│       ├── zoning_bylaws_agent.py   # ZoningBylawsAgent - Comprehensive bylaws discovery:
│       │                            #   - Multi-method discovery (ZBA + Planning Board)
│       │                            #   - Advanced document detection
│       │                            #   - Ecode360 integration
│       │                            #   - Priority-based processing
│       ├── zoning_agent.py          # CombinedZoningAgent - Orchestration layer:
│       │                            #   - Unified interface
│       │                            #   - Agent coordination
│       │                            #   - State management
│       ├── geocode.py               # Multi-provider geocoding services
│       ├── search.py                # Tavily search integration (fallback)
│       ├── scrape.py                # Web scraping and PDF utilities
│       ├── llm.py                   # OpenRouter/Gemini model integration
│       └── zoning.py                # Legacy GIS-based zoning (fallback)
├── pdf_downloads/                   # Organized PDF document storage
├── requirements.txt                 # Python dependencies
└── README.md                       # This documentation
```

## Supported Metrics

The system can extract the following zoning metrics from discovered bylaws:

### Core Zoning Metrics
- **Setback Requirements**: Front, side, rear setbacks (minimum distances)
- **Lot Requirements**: Minimum lot area, frontage, and width
- **Building Coverage**: Maximum lot coverage percentages  
- **Height Restrictions**: Maximum building height limits
- **Parking Requirements**: Off-street parking ratios and specifications
- **Floor Area Ratio (FAR)**: Maximum allowable floor area ratios
- **Density Controls**: Units per acre or similar density metrics
- **Special Requirements**: District-specific requirements and overlays

### Output Format
Results include:
- **Extracted Values**: Specific numeric values with units
- **Confidence Scores**: AI-generated confidence levels
- **Source Citations**: Direct links to source documents and page references
- **Zoning District Context**: Specific district codes and overlay information

## Limitations & Scope

### Geographic Coverage
- **Primary Focus**: Massachusetts municipalities
- **MMA Database**: Relies on Massachusetts Municipal Association member listings
- **Website Variations**: Handles diverse municipal website structures and content management systems

### Document Types Supported
- **Direct PDF Links**: Municipal zoning bylaws in PDF format
- **Ecode360 Integration**: Comprehensive support for ecode360.com hosted documents
- **Legacy Formats**: Limited support for non-standard document formats

### Language Model Limitations
- **Context Windows**: Limited by Gemini model token limits for very large documents (32K tokens for Gemini 2.5 Pro)
- **Accuracy Dependency**: Results depend on source document quality and structure
- **Interpretation Variability**: Language model interpretation may vary for ambiguous regulatory language

## Development & Debugging

### Modular Architecture Benefits
The refactored agent-based architecture provides significant advantages:
- **Separation of Concerns**: Each agent handles specific responsibilities (maps vs. bylaws)
- **Shared Infrastructure**: BaseZoningAgent eliminates code duplication across specialized agents
- **Enhanced Maintainability**: Modular structure makes debugging and updates more focused
- **Efficient Resource Sharing**: Website discovery caching and WebDriver session optimization
- **Backward Compatibility**: CombinedZoningAgent maintains existing API contracts

### Comprehensive Logging Configuration
The system provides extensive structured logging across all agents:
- **Agent-Level Tracking**: Individual logging for BaseZoningAgent, ZoningMapAgent, ZoningBylawsAgent
- **Performance Metrics**: Step-by-step timing and duration tracking with span-based measurement
- **Debug Information**: Detailed process flow, decision points, and method selection rationale
- **Error Tracking**: Full exception handling with stack traces across all agent operations
- **Progress Updates**: Real-time status updates for UI integration with agent-specific messaging

### Testing & Validation  
- **Individual Agent Testing**: Modular design enables isolated testing of map vs. bylaws functionality
- **Shared Infrastructure Testing**: BaseZoningAgent utilities can be tested independently
- **End-to-End Validation**: Complete pipeline testing with real addresses across all agent interactions
- **Error Simulation**: Robust error handling testing across all agent failure modes
- **Method-Specific Testing**: Individual bylaws discovery methods can be tested in isolation

### Enhanced Extensibility
- **Agent-Based Architecture**: Easy addition of new specialized agents (e.g., permit agents, building code agents)
- **Method Expansion**: Simple addition of new discovery methods within ZoningBylawsAgent
- **API Integration**: Streamlined addition of new language model providers or search services through BaseZoningAgent
- **Document Processors**: Extensible document processing pipeline with shared utilities
- **Geographic Expansion**: Framework ready for expansion beyond Massachusetts with agent specialization


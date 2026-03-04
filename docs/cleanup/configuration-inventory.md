# Configuration Inventory - Multimodal Librarian

**Date**: January 5, 2026  
**Purpose**: Complete inventory of all configuration files before cleanup  
**Baseline Status**: ✅ HEALTHY (7/7 tests passed)

## 🎯 Current Production Configuration (WORKING)

### **Active Deployment**
- **Cluster**: `multimodal-librarian-full-ml`
- **Service**: `multimodal-librarian-service`
- **URL**: `http://multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com`
- **Status**: ✅ HEALTHY (all endpoints working)

### **Production Files (KEEP)**
| File | Purpose | Status | Action |
|------|---------|--------|--------|
| `src/multimodal_librarian/main_minimal.py` | **ACTIVE MAIN APP** | ✅ Working | Rename to `main.py` |
| `Dockerfile.full-ml` | **ACTIVE DOCKERFILE** | ✅ Working | Rename to `Dockerfile` |
| `scripts/deploy-full-ml.sh` | **ACTIVE DEPLOY SCRIPT** | ✅ Working | Rename to `deploy.sh` |
| `full-ml-task-def.json` | **ACTIVE TASK DEFINITION** | ✅ Working | Rename to `task-definition.json` |
| `requirements-full-ml.txt` | **ACTIVE REQUIREMENTS** | ✅ Working | Rename to `requirements.txt` |

## 📋 Complete File Inventory

### **Dockerfiles (15+ files)**
```
PRODUCTION (Keep):
✅ Dockerfile.full-ml                    → Rename to Dockerfile

EXPERIMENTAL (Archive):
📦 Dockerfile.learning                   → Archive: experimental/learning-deployment/
📦 Dockerfile.ai-enhanced               → Archive: experimental/ai-enhanced/
📦 Dockerfile.ai-enhanced-documents     → Archive: experimental/ai-enhanced/
📦 Dockerfile.ai-enhanced-documents-minimal → Archive: experimental/ai-enhanced/
📦 Dockerfile.ai-enhanced-minimal       → Archive: experimental/ai-enhanced/
📦 Dockerfile.enhanced-core             → Archive: experimental/enhanced-core/
📦 Dockerfile.enhanced-final            → Archive: experimental/enhanced-final/
📦 Dockerfile.enhanced-minimal          → Archive: experimental/enhanced-minimal/
📦 Dockerfile.enhanced-websocket        → Archive: experimental/websocket-experiments/
📦 Dockerfile.functional-chat           → Archive: experimental/functional-chat/
📦 Dockerfile.full-ml-simple            → Archive: experimental/full-ml-variants/
📦 Dockerfile.self-contained            → Archive: experimental/self-contained/
📦 Dockerfile.test                      → Archive: experimental/testing/

BROKEN/TEMPORARY (Delete):
❌ Dockerfile.patch                      → DELETE
```

### **Main Application Files (8+ files)**
```
PRODUCTION (Keep):
✅ src/multimodal_librarian/main_minimal.py → Rename to main.py

EXPERIMENTAL (Archive):
📦 src/multimodal_librarian/main_learning.py → Archive: experimental/learning-deployment/
📦 src/multimodal_librarian/main_ai_enhanced.py → Archive: experimental/ai-enhanced/
📦 src/multimodal_librarian/main_ai_enhanced_documents_minimal.py → Archive: experimental/ai-enhanced/
📦 src/multimodal_librarian/main_ai_enhanced_minimal.py → Archive: experimental/ai-enhanced/
📦 src/multimodal_librarian/main_minimal_enhanced.py → Archive: experimental/enhanced-minimal/

LEGACY (Archive):
📦 src/multimodal_librarian/main.py      → Archive: experimental/legacy/ (if different from main_minimal.py)
```

### **Deployment Scripts (20+ files)**
```
PRODUCTION (Keep):
✅ scripts/deploy-full-ml.sh             → Rename to deploy.sh

EXPERIMENTAL (Archive):
📦 scripts/deploy-learning-full.sh       → Archive: experimental/learning-deployment/
📦 scripts/deploy-ai-enhanced.sh         → Archive: experimental/ai-enhanced/
📦 scripts/deploy-ai-enhanced-documents.sh → Archive: experimental/ai-enhanced/
📦 scripts/deploy-ai-enhanced-documents-minimal.sh → Archive: experimental/ai-enhanced/
📦 scripts/deploy-ai-enhanced-minimal.sh → Archive: experimental/ai-enhanced/
📦 scripts/deploy-enhanced-final.sh      → Archive: experimental/enhanced-final/
📦 scripts/deploy-enhanced-minimal.sh    → Archive: experimental/enhanced-minimal/
📦 scripts/deploy-websocket-fix.sh       → Archive: experimental/websocket-experiments/
📦 scripts/deploy-functional-chat.sh     → Archive: experimental/functional-chat/
📦 scripts/deploy-self-contained.sh      → Archive: experimental/self-contained/
📦 scripts/deploy-simple.sh              → Archive: experimental/simple/
📦 scripts/deploy-core-enhanced.sh       → Archive: experimental/enhanced-core/

BROKEN/TEMPORARY (Delete):
❌ scripts/patch-*.py                    → DELETE
❌ scripts/quick-fix-*.sh                → DELETE
❌ scripts/quick-patch-*.sh              → DELETE
❌ scripts/patch-current-deployment.py  → DELETE
❌ scripts/patch-live-container.sh       → DELETE
❌ scripts/patch-running-container.py    → DELETE
```

### **Task Definitions (10+ files)**
```
PRODUCTION (Keep):
✅ full-ml-task-def.json                 → Rename to task-definition.json

EXPERIMENTAL (Archive):
📦 ai-enhanced-task-def.json             → Archive: experimental/ai-enhanced/
📦 ai-enhanced-documents-task-def.json   → Archive: experimental/ai-enhanced/
📦 new-simple-enhanced-task-def.json     → Archive: experimental/enhanced-minimal/
📦 simple-task-def.json                  → Archive: experimental/simple/
📦 full-ml-task-def-v2.json              → Archive: experimental/full-ml-variants/
📦 full-ml-standalone-task-def.json      → Archive: experimental/full-ml-variants/

BROKEN/TEMPORARY (Delete):
❌ patched-task-def.json                 → DELETE
❌ current-task-def.json                 → DELETE (if duplicate)
```

### **Requirements Files (10+ files)**
```
PRODUCTION (Keep):
✅ requirements-full-ml.txt               → Rename to requirements.txt

EXPERIMENTAL (Archive):
📦 requirements-learning.txt              → Archive: experimental/learning-deployment/
📦 requirements-ai-enhanced.txt           → Archive: experimental/ai-enhanced/
📦 requirements-ai-enhanced-documents.txt → Archive: experimental/ai-enhanced/
📦 requirements-ai-enhanced-minimal.txt   → Archive: experimental/ai-enhanced/
📦 requirements-enhanced-websocket.txt    → Archive: experimental/websocket-experiments/
📦 requirements-functional.txt            → Archive: experimental/functional-chat/
📦 requirements-minimal-enhanced.txt      → Archive: experimental/enhanced-minimal/
📦 requirements-core.txt                  → Archive: experimental/enhanced-core/

LEGACY (Keep as reference):
📚 requirements.txt                       → Keep (may be legacy version)
```

## 🔗 File Dependencies

### **Production Dependency Chain**
```
main_minimal.py
├── Uses: multimodal-librarian/full-ml/* secrets ✅
├── Imports: Standard multimodal_librarian modules ✅
└── Deployed via: Dockerfile.full-ml → deploy-full-ml.sh → full-ml-task-def.json ✅

Dockerfile.full-ml
├── Uses: requirements-full-ml.txt ✅
├── Copies: src/ directory ✅
└── Exposes: Port 8000 ✅

deploy-full-ml.sh
├── Uses: Dockerfile.full-ml ✅
├── Uses: full-ml-task-def.json ✅
└── Targets: multimodal-librarian-full-ml cluster ✅
```

### **Experimental Dependencies**
```
Learning Deployment:
main_learning.py → Dockerfile.learning → deploy-learning-full.sh
├── Uses: multimodal-librarian/learning/* secrets ❌ (hack)
└── Status: Experimental, not in production

AI Enhanced:
main_ai_enhanced*.py → Dockerfile.ai-enhanced* → deploy-ai-enhanced*.sh
├── Status: Experimental, various versions
└── Dependencies: Complex, multiple variants
```

## 🎯 Categorization Summary

| Category | Count | Action |
|----------|-------|--------|
| **Production** | 5 files | Rename to canonical names |
| **Experimental** | 40+ files | Archive to experimental/ |
| **Broken/Temporary** | 10+ files | Delete completely |
| **Legacy** | 5+ files | Archive or keep as reference |

## 🚨 Critical Dependencies

### **Must Preserve**
- `main_minimal.py` - Active application
- `Dockerfile.full-ml` - Active container build
- `deploy-full-ml.sh` - Active deployment process
- `full-ml-task-def.json` - Active ECS configuration
- `requirements-full-ml.txt` - Active dependencies

### **Safe to Archive**
- All `learning/*` configurations (not in production)
- All `ai-enhanced/*` configurations (experimental)
- All `websocket-experiments/*` (experimental)
- All patch/quick-fix scripts (temporary)

### **Safe to Delete**
- `patched-task-def.json` (temporary)
- All `patch-*.py` scripts (temporary fixes)
- All `quick-fix-*.sh` scripts (temporary)

## ✅ Validation Status

**Current System Health**: 100% (7/7 tests passed)
- ✅ Health endpoint working
- ✅ Database connectivity working  
- ✅ Redis connectivity working
- ✅ API documentation accessible
- ✅ Chat interface working
- ✅ All features enabled correctly
- ✅ Response times optimal (<150ms)

**Ready for Cleanup**: ✅ YES
- Baseline established
- Dependencies mapped
- Safety system in place
- Rollback procedures ready
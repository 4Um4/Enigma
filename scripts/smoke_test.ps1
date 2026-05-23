Write-Host "=== IMPORT TEST ==="

cd backend

python -c "
from app.services.scene_state_manager import SceneStateManager
from app.services.tick_orchestrator import TickOrchestrator
from app.services.spatial.movement_engine import MovementEngine
from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder

print('IMPORT OK')
"

cd ..
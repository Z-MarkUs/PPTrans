"""State management for rollback capability."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Dict, Optional


class StateManager:
    """Manage PPT states for rollback."""
    
    def __init__(self, temp_dir: Optional[Path] = None):
        """Initialize state manager.
        
        Args:
            temp_dir: Temporary directory for storing backups
        """
        self.temp_dir = temp_dir or Path.cwd()
        self.states: Dict[str, Path] = {}  # state_id -> backup_path
    
    def save_state(self, ppt_path: Path) -> str:
        """Save current PPT state for potential rollback.
        
        Args:
            ppt_path: Path to PPT file to backup
            
        Returns:
            State ID for later rollback
        """
        if not ppt_path.exists():
            raise FileNotFoundError(f"PPT file not found: {ppt_path}")
        
        state_id = f"state_{uuid.uuid4().hex[:8]}"
        backup_path = self.temp_dir / f"{ppt_path.stem}_{state_id}.pptx"
        
        # Create backup
        shutil.copy2(ppt_path, backup_path)
        self.states[state_id] = backup_path
        
        return state_id
    
    def rollback(self, ppt_path: Path, state_id: str) -> bool:
        """Rollback to previous state.
        
        Args:
            ppt_path: Path to PPT file to restore
            state_id: State ID from save_state()
            
        Returns:
            True if rollback successful, False otherwise
        """
        if state_id not in self.states:
            return False
        
        backup_path = self.states[state_id]
        if not backup_path.exists():
            return False
        
        try:
            # Restore from backup
            shutil.copy2(backup_path, ppt_path)
            return True
        except Exception:
            return False
    
    def cleanup_state(self, state_id: str):
        """Clean up a specific state backup.
        
        Args:
            state_id: State ID to clean up
        """
        if state_id in self.states:
            backup_path = self.states[state_id]
            try:
                if backup_path.exists():
                    backup_path.unlink()
            except Exception:
                pass
            del self.states[state_id]
    
    def cleanup_all(self):
        """Clean up all state backups."""
        for state_id in list(self.states.keys()):
            self.cleanup_state(state_id)





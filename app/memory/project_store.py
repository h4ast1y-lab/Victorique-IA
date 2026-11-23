import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from app.config import DOCS_DIR
from app.memory.database import get_connection

class ProjectStore:
    def create_project(self, name: str, description: str = "", instructions: str = "") -> Dict[str, Any]:
        p_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, description, instructions, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (p_id, name.strip(), description.strip(), instructions.strip(), now, now)
            )
        return self.get_project(p_id)

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row:
                return dict(row)
        return None

    def list_projects(self) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
            return [dict(r) for r in rows]

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        instructions: Optional[str] = None
    ) -> bool:
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name.strip())
        if description is not None:
            updates.append("description = ?")
            params.append(description.strip())
        if instructions is not None:
            updates.append("instructions = ?")
            params.append(instructions.strip())

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(project_id)

        with get_connection() as conn:
            cur = conn.execute(
                f"UPDATE projects SET {', '.join(updates)} WHERE id = ?",
                params
            )
            return cur.rowcount > 0

    def set_archived(self, project_id: str, archived: bool) -> bool:
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE projects SET archived = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (1 if archived else 0, project_id),
            )
            return cur.rowcount > 0

    def delete_project(self, project_id: str) -> bool:
        with get_connection() as conn:
            files = [
                r["file_path"]
                for r in conn.execute(
                    "SELECT file_path FROM documents WHERE project_id = ?", (project_id,)
                ).fetchall()
            ]
            cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            deleted = cur.rowcount > 0

            if deleted:
                for file_path in files:
                    try:
                        p = Path(file_path).resolve()
                        if p.is_relative_to(DOCS_DIR.resolve()) and p.is_file():
                            p.unlink()
                    except Exception:
                        pass
            return deleted

project_store = ProjectStore()

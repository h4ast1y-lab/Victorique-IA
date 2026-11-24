import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from app.memory.database import get_connection

VALID_CATEGORIES = {"decision", "preference", "project", "fact", "instruction"}
MAX_MEMORY_CHARS = 4000


class MemoryStore:
    @staticmethod
    def _validate(category: str, content: str) -> str:
        category = (category or "").strip().lower()
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Categoria inválida: '{category}'. Use uma de: {', '.join(sorted(VALID_CATEGORIES))}."
            )
        content = (content or "").strip()
        if not content:
            raise ValueError("O conteúdo da memória não pode ficar vazio.")
        if len(content) > MAX_MEMORY_CHARS:
            raise ValueError(f"Memória longa demais (máximo {MAX_MEMORY_CHARS} caracteres).")
        return content

    def add_memory(
        self,
        category: str,
        content: str,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Stores an explicitly created memory. Nothing is saved automatically.
        Categories: 'decision', 'preference', 'project', 'fact', 'instruction'
        """
        content = self._validate(category, content)
        category = category.strip().lower()
        mem_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO memories (id, category, content, project_id, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (mem_id, category, content, project_id, now)
            )
        return self.get_memory(mem_id)

    def get_memory(self, mem_id: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone()
            if row:
                return dict(row)
        return None

    def list_memories(
        self,
        project_id: Optional[str] = None,
        category: Optional[str] = None,
        only_active: bool = True,
        include_global: bool = False,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM memories WHERE 1=1"
        params = []

        if only_active:
            query += " AND is_active = 1"
        if project_id:
            if include_global:
                query += " AND (project_id = ? OR project_id IS NULL)"
            else:
                query += " AND project_id = ?"
            params.append(project_id)
        elif include_global is False and project_id is None:
            # No project selected: only global memories for prompt context.
            pass
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY created_at DESC"

        with get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def update_memory(
        self,
        mem_id: str,
        content: str,
        category: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        content = (content or "").strip()
        if not content:
            raise ValueError("O conteúdo da memória não pode ficar vazio.")
        if len(content) > MAX_MEMORY_CHARS:
            raise ValueError(f"Memória longa demais (máximo {MAX_MEMORY_CHARS} caracteres).")

        updates = ["content = ?"]
        params: list = [content]
        if category:
            category = category.strip().lower()
            if category not in VALID_CATEGORIES:
                raise ValueError(f"Categoria inválida: '{category}'.")
            updates.append("category = ?")
            params.append(category)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)
        params.append(mem_id)

        with get_connection() as conn:
            cur = conn.execute(
                f"UPDATE memories SET {', '.join(updates)} WHERE id = ?",
                params
            )
            return cur.rowcount > 0

    def toggle_memory(self, mem_id: str, is_active: bool) -> bool:
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE memories SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, mem_id)
            )
            return cur.rowcount > 0

    def delete_memory(self, mem_id: str) -> bool:
        with get_connection() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
            return cur.rowcount > 0

    def get_context_for_prompt(
        self,
        project_id: Optional[str] = None,
        user_query: Optional[str] = None,
        max_items: Optional[int] = None,
    ) -> str:
        """
        Retrieves active memories formatted for injection into the prompt.
        With a project: includes global memories plus that project's memories.
        Without a project: only global memories (never another project's data).
        When user_query is provided and there are many memories, ranks by relevance.
        """
        limit = max_items or 6
        with get_connection() as conn:
            if project_id:
                rows = conn.execute(
                    """
                    SELECT * FROM memories
                    WHERE is_active = 1 AND (project_id = ? OR project_id IS NULL)
                    ORDER BY created_at DESC
                    """,
                    (project_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE is_active = 1 AND project_id IS NULL ORDER BY created_at DESC"
                ).fetchall()
            memories = [dict(r) for r in rows]

        if not memories:
            return ""

        # Se houver mais memórias que o limite e tivermos uma query do usuário,
        # ordenamos pela relevância léxica com a query para economizar janela de contexto.
        if len(memories) > limit and user_query:
            import re
            query_terms = [w.lower() for w in re.findall(r"\w+", user_query) if len(w) >= 3]
            def _score_mem(m):
                text = (m["content"] + " " + m["category"]).lower()
                matches = sum(1 for t in query_terms if t in text)
                return matches

            memories.sort(key=_score_mem, reverse=True)
            memories = memories[:limit]
        elif len(memories) > limit:
            memories = memories[:limit]

        lines = ["MEMÓRIAS PERSISTENTES AUTORIZADAS PELO USUÁRIO:"]
        total = 0
        for m in memories:
            line = f"- [{m['category'].upper()}]: {m['content']}"
            total += len(line)
            if total > 6000:
                lines.append("- [AVISO]: memórias adicionais omitidas por limite de contexto.")
                break
            lines.append(line)
        return "\n".join(lines)


memory_store = MemoryStore()

import uuid
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from app.memory.database import get_connection

class ConversationStore:
    def create_conversation(
        self,
        title: str = "Nova Conversa",
        project_id: Optional[str] = None,
        personality_id: Optional[str] = None
    ) -> Dict[str, Any]:
        conv_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, project_id, personality_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (conv_id, title, project_id, personality_id, now, now)
            )
        return self.get_conversation(conv_id)

    def get_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if row:
                return dict(row)
        return None

    def list_conversations(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM conversations WHERE project_id = ? ORDER BY updated_at DESC",
                    (project_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM conversations ORDER BY updated_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    def update_title(self, conv_id: str, new_title: str) -> bool:
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_title, conv_id)
            )
            return cur.rowcount > 0

    def delete_conversation(self, conv_id: str) -> bool:
        with get_connection() as conn:
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            return cur.rowcount > 0

    def get_claude_session(self, conversation_id: str) -> Optional[str]:
        """Claude Code session id this conversation resumes (claude-code mode)."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT claude_session_id FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            return row["claude_session_id"] if row else None

    def set_claude_session(self, conversation_id: str, session_id: Optional[str]) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE conversations SET claude_session_id = ? WHERE id = ?",
                (session_id, conversation_id),
            )

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        tool_trace: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        msg_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        sources_json = json.dumps(sources, ensure_ascii=False) if sources else None
        tool_trace_json = (
            json.dumps(tool_trace, ensure_ascii=False, default=str) if tool_trace else None
        )

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO messages
                    (id, conversation_id, role, content, sources_json, tool_trace_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (msg_id, conversation_id, role, content, sources_json, tool_trace_json, now)
            )
            # Update parent conversation timestamp
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id)
            )

        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "sources": sources,
            "tool_trace": tool_trace,
            "created_at": now
        }

    def get_messages(self, conversation_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            # Take the most recent N messages, then present them chronologically.
            rows = conn.execute(
                """
                SELECT id, conversation_id, role, content, sources_json,
                       tool_trace_json, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (conversation_id, limit)
            ).fetchall()
            rows = list(reversed(rows))

            messages = []
            for r in rows:
                item = dict(r)
                if item.get("sources_json"):
                    try:
                        item["sources"] = json.loads(item["sources_json"])
                    except json.JSONDecodeError:
                        item["sources"] = None
                else:
                    item["sources"] = None
                del item["sources_json"]
                raw_trace = item.pop("tool_trace_json", None)
                try:
                    item["tool_trace"] = json.loads(raw_trace) if raw_trace else None
                except json.JSONDecodeError:
                    item["tool_trace"] = None
                messages.append(item)
            return messages

    def search_conversations(
        self, query: str, project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            q = f"%{query}%"
            if project_id:
                rows = conn.execute(
                    """
                    SELECT DISTINCT c.id, c.title, c.updated_at
                    FROM conversations c
                    LEFT JOIN messages m ON c.id = m.conversation_id
                    WHERE (c.title LIKE ? OR m.content LIKE ?) AND c.project_id = ?
                    ORDER BY c.updated_at DESC
                    """,
                    (q, q, project_id)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT c.id, c.title, c.updated_at
                    FROM conversations c
                    LEFT JOIN messages m ON c.id = m.conversation_id
                    WHERE (c.title LIKE ? OR m.content LIKE ?) AND c.project_id IS NULL
                    ORDER BY c.updated_at DESC
                    """,
                    (q, q)
                ).fetchall()
            return [dict(r) for r in rows]

    def export_conversation(self, conversation_id: str, export_format: str = "json") -> str:
        conv = self.get_conversation(conversation_id)
        if not conv:
            raise ValueError("Conversation not found")
        messages = self.get_messages(conversation_id)

        if export_format == "json":
            return json.dumps({"conversation": conv, "messages": messages}, indent=2, ensure_ascii=False)
        elif export_format == "md":
            lines = [f"# {conv['title']}\n*Criada em: {conv['created_at']}*\n\n---\n"]
            for m in messages:
                author = "👤 Usuário" if m["role"] == "user" else "🤖 Assistente"
                lines.append(f"### {author}\n{m['content']}\n")
                if m.get("sources"):
                    lines.append("\n**Fontes consultadas:**")
                    for s in m["sources"]:
                        lines.append(f"- *{s.get('document', 'Documento')}* (pág. {s.get('page', '?')})")
                    lines.append("\n")
            return "\n".join(lines)
        else:
            # Plain text
            lines = [f"{conv['title']}\nData: {conv['created_at']}\n{'='*40}\n"]
            for m in messages:
                author = "Usuário" if m["role"] == "user" else "Assistente"
                lines.append(f"[{author}]: {m['content']}\n")
            return "\n".join(lines)

conversation_store = ConversationStore()

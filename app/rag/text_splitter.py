from typing import List, Dict, Any

class TextSplitter:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 60):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_pages(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Takes page objects [{"page": int, "text": str}]
        Returns chunks [{"chunk_index": int, "page": int, "text": str}]
        """
        chunks = []
        chunk_idx = 0

        for p in pages:
            page_num = p["page"]
            text = p["text"]
            
            if len(text) <= self.chunk_size:
                chunks.append({
                    "chunk_index": chunk_idx,
                    "page": page_num,
                    "text": text
                })
                chunk_idx += 1
                continue

            # Sliding window split
            start = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                
                # Try to break at a paragraph or sentence boundary if possible
                if end < len(text):
                    last_period = text.rfind(". ", start, end)
                    last_newline = text.rfind("\n", start, end)
                    break_point = max(last_period, last_newline)
                    if break_point > start + (self.chunk_size // 2):
                        end = break_point + 1

                chunk_text = text[start:end].strip()
                if chunk_text:
                    chunks.append({
                        "chunk_index": chunk_idx,
                        "page": page_num,
                        "text": chunk_text
                    })
                    chunk_idx += 1

                if end >= len(text):
                    break
                start = max(start + 1, end - self.chunk_overlap)

        return chunks

text_splitter = TextSplitter()

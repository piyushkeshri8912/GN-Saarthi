from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List, Tuple, Dict, Any

def chunk_document_pages(pages_data: List[Tuple[int, str]], doc_id: str = None) -> List[Dict[str, Any]]:
    """
    Splits document text into overlapping chunks that can span page boundaries.
    Preserves page_start and page_end range metadata, plus page for backward compatibility.
    Uses LangChain's RecursiveCharacterTextSplitter configured by tiktoken tokens.
    
    Config:
      - chunk_size: 512 tokens
      - chunk_overlap: 64 tokens
    """
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=512,
        chunk_overlap=64,
        encoding_name="cl100k_base"
    )
    
    # 1. Concatenate text from pages and record start/end offsets for each page
    concatenated_text = ""
    page_intervals = []
    
    for page_num, text in pages_data:
        text = text.strip()
        if not text:
            continue  # Skip empty pages cleanly
            
        start_offset = len(concatenated_text)
        if concatenated_text:
            concatenated_text += "\n\n"
            start_offset = len(concatenated_text)
            
        concatenated_text += text
        end_offset = len(concatenated_text)
        page_intervals.append({
            "page_num": page_num,
            "start": start_offset,
            "end": end_offset
        })
        
    if not concatenated_text or not page_intervals:
        return []
        
    # 2. Split concatenated text recursively
    split_texts = text_splitter.split_text(concatenated_text)
    
    # 3. Track positions and determine overlapping pages
    chunks = []
    current_search_index = 0
    
    for idx, chunk_text in enumerate(split_texts):
        chunk_start = concatenated_text.find(chunk_text, current_search_index)
        if chunk_start == -1:
            # Fallback to absolute search if offset fails
            chunk_start = concatenated_text.find(chunk_text)
            if chunk_start == -1:
                chunk_start = current_search_index
                
        chunk_end = chunk_start + len(chunk_text)
        current_search_index = chunk_start + len(chunk_text)
        
        overlapping_pages = []
        for interval in page_intervals:
            # Check overlap: chunk_start < interval["end"] and chunk_end > interval["start"]
            if chunk_start < interval["end"] and chunk_end > interval["start"]:
                overlapping_pages.append(interval["page_num"])
                
        if not overlapping_pages:
            # Fallback to closest page if no direct character range overlap is found
            closest_page = page_intervals[0]["page_num"]
            min_dist = float("inf")
            for interval in page_intervals:
                dist = min(abs(chunk_start - interval["start"]), abs(chunk_start - interval["end"]))
                if dist < min_dist:
                    min_dist = dist
                    closest_page = interval["page_num"]
            page_start = closest_page
            page_end = closest_page
        else:
            page_start = min(overlapping_pages)
            page_end = max(overlapping_pages)
            
        chunks.append({
            "text": chunk_text,
            "page": page_start,          # Backward compatibility
            "page_start": page_start,
            "page_end": page_end,
            "doc_id": doc_id,
            "chunk_index": idx
        })
        
    return chunks

def split_text_by_page(pages_data: List[Dict[str, Any]], doc_id: str = None) -> List[Dict[str, Any]]:
    """
    Compatibility wrapper matching the test suite signature.
    Converts list of dicts to list of tuples and chunks them.
    """
    formatted = [(p["page_num"], p["text"]) for p in pages_data]
    return chunk_document_pages(formatted, doc_id=doc_id)


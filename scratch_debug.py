import re

edu_text = """Vellore Institute of Technology, Vellore September 2022 - 2026 (Expected)
Bachelor of Technology in Computer Science and Engineering and Business Systems CGPA: 9.04/10
Scindia Kanya Vidyalaya, Gwalior July 2019 - June 2021
AISSCE Percentage: 94.6%"""

raw_lines = [l.strip() for l in edu_text.split('\n') if l.strip()]

HEADER_KEYWORDS = {"year", "degree", "certificate", "institute", "cgpa", "board", "passing", "percentage", "mark", "gpa", "institutions", "degrees"}
DEGREE_KEYWORDS = ["B.Tech", "B.E.", "B.Sc", "Bachelor", "M.Tech", "M.Sc", "Master", "MBA", "PhD", "Class XII", "Class X", "12th", "10th", "HSC", "SSC", "CBSE", "ICSE"]
INSTITUTION_INDICATORS = ["Institute", "University", "School", "Vidyalaya", "College", "Academy"]

def is_header_line(text: str) -> bool:
    words = set(re.findall(r'\b\w+\b', text.lower()))
    intersect = words.intersection(HEADER_KEYWORDS)
    if len(intersect) >= 2 and not re.search(r'\b(?:19|20)\d{2}\b', text):
        return True
    return False

def has_school_indicator(text: str) -> bool:
    return any(re.search(rf'\b{re.escape(ind)}\b', text, re.IGNORECASE) for ind in INSTITUTION_INDICATORS)

# Identify year lines
year_lines_info = []
for idx, line in enumerate(raw_lines):
    matches = re.findall(r'\b(?:19|20)\d{2}\b', line)
    if matches:
        end_year = int(matches[-1])
        year_lines_info.append({
            "idx": idx,
            "end_year": end_year,
            "line": line
        })

claimed_indices = set()
# 1. Backward scan
for k, info in enumerate(year_lines_info):
    d_idx = info["idx"]
    claimed_indices.add(d_idx)
    
    backward_lines = []
    prev_d_idx = year_lines_info[k - 1]["idx"] if k > 0 else -1
    for b_idx in range(d_idx - 1, prev_d_idx, -1):
        line_text = raw_lines[b_idx]
        if is_header_line(line_text):
            break
        if b_idx in claimed_indices:
            break
        if has_school_indicator(raw_lines[d_idx]):
            break
        backward_lines.insert(0, b_idx)
        claimed_indices.add(b_idx)
        if has_school_indicator(line_text):
            break
    info["backward_lines"] = backward_lines

# 2. Forward scan
for k, info in enumerate(year_lines_info):
    d_idx = info["idx"]
    forward_lines = []
    
    next_limit = len(raw_lines)
    if k + 1 < len(year_lines_info):
        next_info = year_lines_info[k + 1]
        if next_info["backward_lines"]:
            next_limit = next_info["backward_lines"][0]
        else:
            next_limit = next_info["idx"]
            
    for f_idx in range(d_idx + 1, next_limit):
        forward_lines.append(f_idx)
        claimed_indices.add(f_idx)
    info["forward_lines"] = forward_lines

# Print results
for k, info in enumerate(year_lines_info):
    entry_line_indices = info["backward_lines"] + [info["idx"]] + info["forward_lines"]
    entry_lines = [raw_lines[idx] for idx in entry_line_indices]
    print(f"Entry {k}:")
    for l in entry_lines:
        print(f"  {l}")

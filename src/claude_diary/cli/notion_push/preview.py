"""Flattening Notion block payloads back into readable text.

`--dry-run` has to show what the page will look like without calling Notion,
and the run artifacts save the same rendering to `preview.md`. Both read the
real block payload rather than a parallel formatter, so a preview cannot
drift from what a push would actually create.
"""


def _blocks_to_preview_lines(blocks, max_lines=80):
    lines = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "heading_2":
            lines.append("## %s" % _block_text(block, "heading_2"))
        elif block_type == "callout":
            lines.append("[Callout] %s" % _block_text(block, "callout"))
        elif block_type == "to_do":
            checked = "x" if block.get("to_do", {}).get("checked") else " "
            lines.append("- [%s] %s" % (checked, _block_text(block, "to_do")))
        elif block_type == "bulleted_list_item":
            lines.append("- %s" % _block_text(block, "bulleted_list_item"))
        elif block_type == "toggle":
            lines.append("> %s" % _block_text(block, "toggle"))
            for child in block.get("toggle", {}).get("children", [])[:20]:
                child_type = child.get("type")
                if child_type:
                    lines.append("  - %s" % _block_text(child, child_type))
        elif block_type == "table":
            lines.extend(_table_preview_lines(block))
        if len(lines) >= max_lines:
            lines.append("... (%d more block lines)" % (len(blocks) - max_lines))
            break
    return lines


def _table_preview_lines(block):
    rows = []
    for child in block.get("table", {}).get("children", []):
        cells = child.get("table_row", {}).get("cells", [])
        row = " | ".join(_rich_text_plain(cell) for cell in cells)
        if row.strip():
            rows.append(row)
    return rows


def _block_text(block, block_type):
    return _rich_text_plain(block.get(block_type, {}).get("rich_text", []))


def _rich_text_plain(rich_text):
    parts = []
    for item in rich_text or []:
        text = item.get("plain_text")
        if text is None:
            text = (item.get("text") or {}).get("content")
        if text:
            parts.append(text)
    return "".join(parts)

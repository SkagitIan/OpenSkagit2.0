import json


def to_json(case_file: dict) -> str:
    return json.dumps(case_file, indent=2, default=str)


def to_markdown(case_file: dict) -> str:
    lines = [
        "# Civic Intelligence Case File",
        f"\n**Entity:** {case_file.get('entity', 'Unknown')}",
        f"**Question:** {case_file.get('question', '')}",
        f"**Confidence:** {case_file.get('confidence', 'unknown').upper()}",
        f"**Generated:** {case_file.get('created_at', '')}",
        "\n---\n",
        "## Answer\n",
        case_file.get("answer", "No answer generated."),
        "\n## Evidence\n",
    ]

    for item in case_file.get("evidence", []):
        lines.append(f"### {item.get('source_name', item.get('source_id', 'Unknown'))}")
        data = item.get("data", [])
        records = data if isinstance(data, list) else [data]
        for record in records[:3]:
            if isinstance(record, dict):
                for key, value in record.items():
                    lines.append(f"- **{key}:** {value}")
        lines.append("")

    if case_file.get("missing"):
        lines.append("## Missing Evidence\n")
        for item in case_file["missing"]:
            lines.append(f"- {item}")

    lines.append("\n## Sources Queried\n")
    for source_id in case_file.get("sources_queried", []):
        lines.append(f"- {source_id}")

    return "\n".join(lines)

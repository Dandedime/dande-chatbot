import re

def extract_sql(response):
    """Extract sql query from response text"""
    sql_match = re.search(r"```sql\n(.*)\n```", response, re.DOTALL)
    if sql_match:
        sql = sql_match.group(1)
        return sql

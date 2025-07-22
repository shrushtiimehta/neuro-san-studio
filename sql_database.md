# Database Assistant System

The **Database Assistant System** is a framework for managing SQLite databases just using natural language. 
It leverages a `database_manager` agent for natural language interpretation and formatting, and delegates database execution tasks to a backend `sql_developer` tool.

This system supports schema operations, record manipulation, and database introspection through clearly defined JSON payloads and delegated responsibility.

---

## File

[sql_database.hocon](../../registries/sql_database.hocon)

---

## Prerequisites

### 1. Enable the Agent in `manifest.hocon`

This agent is **disabled by default**. Enable it by setting its value to `true` in the `manifest.hocon` configuration:

```hocon
sql_database.hocon: true
```

### 2. Set the SQLite Database Path via environment variables

```bash
export DATABASE_PATH=/relative/path/to/file.db
```

---

## Description

This system is composed of two core agents:

- **database_manager**: Frontman agent responsible for interpreting natural language queries and formatting them into valid JSON payloads for downstream execution.
- **sql_developer**: Backend executor agent that directly interacts with an SQLite database using the `DatabaseTool` class and performs the required SQL operations.

The assistant supports the following database actions:

1. **Create a table**
2. **Insert a row**
3. **Fetch one row**
4. **Fetch all rows**
5. **Update row data**
6. **Delete a row**
7. **Analyze table or database**

---

## Example Queries

```text
Create a table named `users` with fields: id (integer), name (text), and email (text). The id should be the primary key.
```

```text
Add a new user with id 001, name Sarah, and email sarah@cognizant.com. Then update her email to sarah@cail.com.
```

```text
Get the user details where the id is 001. Also give me the full list of all users.
```

```text
Tell me how many rows and columns are in the `users` table. Also give a full structural summary of the entire database.
```

Note: Be very careful with spelling and case sensitivity. Table names, column names, and values must exactly match what exists in the database.

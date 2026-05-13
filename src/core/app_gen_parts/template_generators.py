"""
ZENIC-AGENTS - Template Generator Mixin

HTML + CSS template generators:
_gen_base_template, _gen_dashboard_template, _gen_list_template,
_gen_form_template, _gen_css
"""


class TemplateGeneratorMixin:
    """Mixin with HTML/CSS template generation methods for AppGenerator."""

    def _gen_base_template(self, plan, project_name: str) -> str:
        """Genera templates/base.html - Layout base."""
        return f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{{{% block title %}}}}{project_name}{{{{% endblock %}}}}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <nav class="navbar">
        <div class="nav-brand">
            <a href="/">{project_name}</a>
        </div>
        <div class="nav-links">
            <a href="/">Dashboard</a>
            {''.join(f'<a href="/{e["name"].lower()}s">{e["name"]}s</a>' for e in plan.entities[:5])}
        </div>
    </nav>
    <main class="container">
        {{{{% block content %}}}}
        {{{{% endblock %}}}}
    </main>
    <footer class="footer">
        <p>{project_name} - Powered by ZENIC-AGENTS</p>
    </footer>
</body>
</html>'''

    def _gen_dashboard_template(self, plan, project_name: str) -> str:
        """Genera templates/dashboard.html."""
        entity_cards = []
        for entity in plan.entities[:4]:
            name = entity.get("name", "Item")
            name_lower = name.lower()
            entity_cards.append(f'''
            <div class="card">
                <h3>{name}s</h3>
                <p>Gestionar {name_lower}s</p>
                <a href="/{name_lower}s" class="btn">Ver {name}s</a>
            </div>''')

        cards_str = "\n".join(entity_cards) if entity_cards else '''
            <div class="card">
                <h3>Bienvenido</h3>
                <p>Sistema listo para usar.</p>
            </div>'''

        return f'''{{% extends "base.html" %}}

{{% block title %}}}}Dashboard - {project_name}{{% endblock %}}

{{% block content %}}}}
<h1>Dashboard</h1>
<div class="grid">
    {cards_str}
</div>

{{% if stats %}}}}
<div class="stats-section">
    <h2>Estadísticas</h2>
    <div class="grid">
        {{% for key, value in stats.items() %}}}}
        <div class="stat-card">
            <span class="stat-value">{{{{ value }}}}</span>
            <span class="stat-label">{{{{ key }}}}</span>
        </div>
        {{% endfor %}}}}
    </div>
</div>
{{% endif %}}}}
{{% endblock %}}'''

    def _gen_list_template(self, plan, project_name: str) -> str:
        """Genera templates/list.html - Lista de entidades con CRUD."""
        return '''{% extends "base.html" %}

{% block title %}{{ entity_name }}s - {{ app_name }}{% endblock %}

{% block content %}
<div class="page-header">
    <h1>{{ entity_name }}s</h1>
    <div class="actions">
        <form method="get" class="search-form">
            <input type="text" name="search" placeholder="Buscar..." value="{{ search|default('') }}">
            <button type="submit" class="btn">Buscar</button>
        </form>
        <button class="btn btn-primary" onclick="openCreateForm()">+ Nuevo {{ entity_name }}</button>
    </div>
</div>

<div class="table-container">
    <table class="data-table">
        <thead>
            <tr>
                <th>ID</th>
                <th>Nombre</th>
                <th>Creado</th>
                <th>Acciones</th>
            </tr>
        </thead>
        <tbody>
            {% for item in items %}
            <tr>
                <td>{{ item.id }}</td>
                <td>{{ item.name|default('') }}</td>
                <td>{{ item.created_at|default('') }}</td>
                <td class="actions-cell">
                    <button class="btn btn-sm" onclick="editItem({{ item.id }})">Editar</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteItem({{ item.id }})">Eliminar</button>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<div class="pagination">
    {% if page > 1 %}
    <a href="?page={{ page - 1 }}" class="btn">&laquo; Anterior</a>
    {% endif %}
    <span>Página {{ page }}</span>
</div>

<!-- Create/Edit Modal -->
<div id="itemModal" class="modal" style="display:none">
    <div class="modal-content">
        <h2 id="modalTitle">Nuevo {{ entity_name }}</h2>
        <form id="itemForm">
            <div class="form-group">
                <label>Nombre</label>
                <input type="text" name="name" required>
            </div>
            <div class="form-actions">
                <button type="submit" class="btn btn-primary">Guardar</button>
                <button type="button" class="btn" onclick="closeModal()">Cancelar</button>
            </div>
        </form>
    </div>
</div>

<script>
const entityName = "{{ entity_name_lower }}";
let editingId = null;

function openCreateForm() {
    editingId = null;
    document.getElementById('modalTitle').textContent = 'Nuevo ' + entityName;
    document.getElementById('itemForm').reset();
    document.getElementById('itemModal').style.display = 'block';
}

function editItem(id) {
    editingId = id;
    document.getElementById('modalTitle').textContent = 'Editar ' + entityName;
    fetch('/api/' + entityName + 's/' + id)
        .then(r => r.json())
        .then(data => {
            const form = document.getElementById('itemForm');
            form.name.value = data.name || '';
            document.getElementById('itemModal').style.display = 'block';
        });
}

function deleteItem(id) {
    if (confirm('Eliminar este elemento?')) {
        fetch('/api/' + entityName + 's/' + id, {method: 'DELETE'})
            .then(() => location.reload());
    }
}

function closeModal() {
    document.getElementById('itemModal').style.display = 'none';
}

document.getElementById('itemForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const data = {name: this.name.value};
    const url = editingId
        ? '/api/' + entityName + 's/' + editingId
        : '/api/' + entityName + 's';
    const method = editingId ? 'PUT' : 'POST';
    fetch(url, {method: method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)})
        .then(() => { closeModal(); location.reload(); });
});
</script>
{% endblock %}'''

    def _gen_form_template(self, plan, project_name: str) -> str:
        """Genera templates/form.html - Formulario de creación/edición."""
        fields_html = []
        for entity in plan.entities[:1]:
            for f in entity.get("fields", []):
                parts = f.split(":")
                fname = parts[0]
                ftype = parts[1] if len(parts) > 1 else "str"
                input_type = {"int": "number", "float": "number", "datetime": "datetime-local",
                              "bool": "checkbox"}.get(ftype, "text")
                fields_html.append(f'''
            <div class="form-group">
                <label for="{fname}">{fname.replace("_", " ").title()}</label>
                <input type="{input_type}" id="{fname}" name="{fname}">
            </div>''')

        fields_str = "\n".join(fields_html) if fields_html else '''
            <div class="form-group">
                <label for="name">Nombre</label>
                <input type="text" id="name" name="name" required>
            </div>'''

        return '''{% extends "base.html" %}

{% block title %}{{ entity_name }} - Form{% endblock %}

{% block content %}
<div class="page-header">
    <h1>{{ entity_name }}</h1>
</div>
<form class="form-container" method="POST" action="/api/{{ entity_name_lower }}s">
''' + fields_str + '''
    <div class="form-actions">
        <button type="submit" class="btn btn-primary">Guardar</button>
        <a href="/{{ entity_name_lower }}s" class="btn">Cancelar</a>
    </div>
</form>
{% endblock %}'''

    def _gen_css(self, plan, project_name: str) -> str:
        """Genera static/style.css - Estilos CSS profesionales."""
        return '''/* ZENIC-AGENTS - Generated Styles */
:root {
    --primary: #2563eb;
    --primary-dark: #1d4ed8;
    --danger: #dc2626;
    --success: #16a34a;
    --warning: #f59e0b;
    --bg: #f8fafc;
    --card-bg: #ffffff;
    --text: #1e293b;
    --text-muted: #64748b;
    --border: #e2e8f0;
    --radius: 8px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
}

/* Navbar */
.navbar {
    background: var(--primary);
    color: white;
    padding: 0 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: 56px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.nav-brand a { color: white; text-decoration: none; font-size: 1.25rem; font-weight: 700; }
.nav-links a { color: rgba(255,255,255,0.9); text-decoration: none; margin-left: 1.5rem; font-size: 0.95rem; }
.nav-links a:hover { color: white; }

/* Container */
.container { max-width: 1200px; margin: 2rem auto; padding: 0 1.5rem; }

/* Grid */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; }

/* Cards */
.card {
    background: var(--card-bg);
    border-radius: var(--radius);
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid var(--border);
}
.card h3 { margin-bottom: 0.5rem; color: var(--primary); }
.card p { color: var(--text-muted); margin-bottom: 1rem; }

/* Stat cards */
.stat-card {
    background: var(--card-bg);
    border-radius: var(--radius);
    padding: 1.25rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid var(--border);
}
.stat-value { display: block; font-size: 2rem; font-weight: 700; color: var(--primary); }
.stat-label { display: block; font-size: 0.85rem; color: var(--text-muted); margin-top: 0.25rem; }

/* Buttons */
.btn {
    display: inline-block;
    padding: 0.5rem 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--card-bg);
    color: var(--text);
    text-decoration: none;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.15s ease;
}
.btn:hover { background: var(--bg); }
.btn-primary { background: var(--primary); color: white; border-color: var(--primary); }
.btn-primary:hover { background: var(--primary-dark); }
.btn-danger { background: var(--danger); color: white; border-color: var(--danger); }
.btn-sm { padding: 0.25rem 0.75rem; font-size: 0.8rem; }

/* Table */
.table-container { overflow-x: auto; margin-top: 1rem; }
.data-table { width: 100%; border-collapse: collapse; background: var(--card-bg); border-radius: var(--radius); overflow: hidden; }
.data-table th, .data-table td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }
.data-table th { background: var(--bg); font-weight: 600; color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; }
.data-table tr:hover { background: rgba(37, 99, 235, 0.03); }
.actions-cell { white-space: nowrap; }
.actions-cell .btn { margin-right: 0.25rem; }

/* Page header */
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
.actions { display: flex; gap: 0.75rem; align-items: center; }
.search-form { display: flex; gap: 0.5rem; }
.search-form input { padding: 0.5rem; border: 1px solid var(--border); border-radius: var(--radius); }

/* Forms */
.form-container { max-width: 600px; background: var(--card-bg); padding: 2rem; border-radius: var(--radius); box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.form-group { margin-bottom: 1.25rem; }
.form-group label { display: block; margin-bottom: 0.25rem; font-weight: 500; }
.form-group input, .form-group select, .form-group textarea {
    width: 100%; padding: 0.5rem; border: 1px solid var(--border); border-radius: var(--radius); font-size: 0.95rem;
}
.form-actions { display: flex; gap: 0.75rem; margin-top: 1.5rem; }

/* Modal */
.modal { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; }
.modal-content { background: var(--card-bg); padding: 2rem; border-radius: var(--radius); max-width: 500px; width: 90%; }

/* Pagination */
.pagination { display: flex; justify-content: center; gap: 1rem; margin-top: 2rem; align-items: center; }

/* Footer */
.footer { text-align: center; padding: 2rem; color: var(--text-muted); font-size: 0.85rem; margin-top: 3rem; }

/* Responsive */
@media (max-width: 768px) {
    .navbar { padding: 0 1rem; }
    .container { padding: 0 1rem; }
    .page-header { flex-direction: column; gap: 1rem; }
    .actions { flex-direction: column; width: 100%; }
    .search-form { width: 100%; }
    .search-form input { flex: 1; }
}
'''

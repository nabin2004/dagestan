/**
 * Dagestan Graph Visualizer — Frontend Application
 *
 * Live, interactive graph visualization with auto-refresh,
 * node/edge inspection, filtering, and statistics.
 */

// ════════════════════════════════════════════════════════════
// Configuration
// ════════════════════════════════════════════════════════════

const NODE_COLORS = {
    entity:     { bg: '#1f3a5f', border: '#58a6ff', font: '#58a6ff', highlight: { bg: '#264d7a', border: '#79b8ff' } },
    concept:    { bg: '#2d1f4e', border: '#bc8cff', font: '#bc8cff', highlight: { bg: '#3d2d6b', border: '#d2a8ff' } },
    event:      { bg: '#3d2c0f', border: '#d29922', font: '#d29922', highlight: { bg: '#4d3a1a', border: '#e3b341' } },
    preference: { bg: '#0f2d1a', border: '#3fb950', font: '#3fb950', highlight: { bg: '#1a3d25', border: '#56d364' } },
    goal:       { bg: '#3d1014', border: '#f85149', font: '#f85149', highlight: { bg: '#5a1a20', border: '#ff7b72' } },
};

const EDGE_COLORS = {
    relates_to:      '#484f58',
    caused:          '#d29922',
    contradicts:     '#f85149',
    happened_before: '#8b949e',
    has_preference:  '#3fb950',
    wants:           '#f85149',
};

const NODE_SHAPES = {
    entity:     'dot',
    concept:    'diamond',
    event:      'star',
    preference: 'triangle',
    goal:       'hexagon',
};

const NODE_SIZES = {
    entity:     25,
    concept:    22,
    event:      20,
    preference: 18,
    goal:       22,
};


// ════════════════════════════════════════════════════════════
// State
// ════════════════════════════════════════════════════════════

let network = null;
let graphData = { nodes: [], edges: [] };
let visNodes = new vis.DataSet();
let visEdges = new vis.DataSet();
let currentHash = '';
let pollTimer = null;
let pollInterval = 2000;
let typeChart = null;
let confChart = null;
let eventSource = null;  // SSE connection

// Filters
let activeTypeFilters = new Set(['entity', 'concept', 'event', 'preference', 'goal']);
let searchQuery = '';
let confMinFilter = 0;
let confMaxFilter = 1;

// Diff tracking
let previousNodeIds = new Set();
let previousEdgeIds = new Set();
let newNodeIds = new Set();    // Nodes added in last update
let removedNodeIds = new Set(); // Nodes removed in last update


// ════════════════════════════════════════════════════════════
// Initialization
// ════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    initGraph();
    initControls();
    initCharts();
    loadFileList();
    fetchAndRender();
    startLiveUpdates();
    log('info', 'Visualizer initialized');
});


function initGraph() {
    const container = document.getElementById('graphCanvas');
    const options = {
        nodes: {
            borderWidth: 2,
            borderWidthSelected: 3,
            font: {
                color: '#e6edf3',
                size: 13,
                face: '-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif',
                strokeWidth: 3,
                strokeColor: '#0d1117',
            },
            shadow: {
                enabled: true,
                color: 'rgba(0,0,0,0.3)',
                size: 8,
                x: 0,
                y: 2,
            },
        },
        edges: {
            width: 1.5,
            selectionWidth: 2.5,
            smooth: {
                enabled: true,
                type: 'continuous',
                roundness: 0.3,
            },
            arrows: {
                to: { enabled: true, scaleFactor: 0.6, type: 'arrow' },
            },
            font: {
                color: '#484f58',
                size: 10,
                strokeWidth: 2,
                strokeColor: '#0d1117',
                align: 'middle',
            },
        },
        physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -40,
                centralGravity: 0.005,
                springLength: 150,
                springConstant: 0.04,
                damping: 0.4,
                avoidOverlap: 0.5,
            },
            stabilization: {
                enabled: true,
                iterations: 200,
                updateInterval: 25,
            },
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            zoomView: true,
            dragView: true,
            multiselect: true,
        },
        layout: {
            improvedLayout: true,
        },
    };

    network = new vis.Network(container, { nodes: visNodes, edges: visEdges }, options);

    // Event listeners
    network.on('click', onNetworkClick);
    network.on('doubleClick', onNetworkDoubleClick);
    network.on('hoverNode', () => { container.style.cursor = 'pointer'; });
    network.on('blurNode', () => { container.style.cursor = 'default'; });
    network.on('stabilizationProgress', (params) => {
        const pct = Math.round(params.iterations / params.total * 100);
        document.getElementById('overlayText').textContent = `Stabilizing... ${pct}%`;
    });
    network.on('stabilizationIterationsDone', () => {
        document.getElementById('graphOverlay').classList.add('hidden');
    });
}


function initControls() {
    // Refresh button
    document.getElementById('btnRefresh').addEventListener('click', () => {
        fetchAndRender(true);
    });

    // Fit view
    document.getElementById('btnFitView').addEventListener('click', () => {
        network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
    });

    // Refresh interval
    document.getElementById('refreshInterval').addEventListener('change', (e) => {
        pollInterval = parseInt(e.target.value, 10);
        const indicator = document.getElementById('liveIndicator');
        if (pollInterval === 0) {
            indicator.classList.add('paused');
            if (eventSource) { eventSource.close(); eventSource = null; }
            if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
            log('info', 'Live refresh paused');
        } else {
            indicator.classList.remove('paused');
            startLiveUpdates();
            log('info', `Live refresh: ${pollInterval / 1000}s`);
        }
    });

    // File selector
    document.getElementById('fileSelect').addEventListener('change', (e) => {
        if (e.target.value) {
            switchFile(e.target.value);
        }
    });

    // Search
    document.getElementById('searchInput').addEventListener('input', (e) => {
        searchQuery = e.target.value.toLowerCase();
        applyFilters();
    });

    // Confidence range
    document.getElementById('confMin').addEventListener('input', (e) => {
        confMinFilter = parseInt(e.target.value, 10) / 100;
        document.getElementById('confMinLabel').textContent = `${e.target.value}%`;
        applyFilters();
    });
    document.getElementById('confMax').addEventListener('input', (e) => {
        confMaxFilter = parseInt(e.target.value, 10) / 100;
        document.getElementById('confMaxLabel').textContent = `${e.target.value}%`;
        applyFilters();
    });
}


function initCharts() {
    const chartOpts = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: true,
                position: 'bottom',
                labels: { color: '#8b949e', font: { size: 10 }, boxWidth: 12 },
            },
        },
    };

    typeChart = new Chart(document.getElementById('typeChart'), {
        type: 'doughnut',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: [],
                borderColor: '#21262d',
                borderWidth: 2,
            }],
        },
        options: chartOpts,
    });

    confChart = new Chart(document.getElementById('confChart'), {
        type: 'bar',
        data: {
            labels: ['0-20%', '20-40%', '40-60%', '60-80%', '80-100%'],
            datasets: [{
                label: 'Nodes',
                data: [0, 0, 0, 0, 0],
                backgroundColor: ['#f85149', '#db6d28', '#d29922', '#58a6ff', '#3fb950'],
                borderRadius: 3,
            }],
        },
        options: {
            ...chartOpts,
            plugins: { ...chartOpts.plugins, legend: { display: false } },
            scales: {
                x: { ticks: { color: '#8b949e', font: { size: 9 } }, grid: { display: false } },
                y: { ticks: { color: '#8b949e', font: { size: 9 }, stepSize: 1 }, grid: { color: '#21262d' } },
            },
        },
    });
}


// ════════════════════════════════════════════════════════════
// Data Fetching
// ════════════════════════════════════════════════════════════

async function fetchAndRender(force = false) {
    try {
        // Check if data changed (unless forced)
        if (!force) {
            const hashResp = await fetch('/api/graph/hash');
            const hashData = await hashResp.json();
            if (hashData.hash === currentHash && currentHash !== '') {
                return; // No change
            }
        }

        const resp = await fetch('/api/graph');
        const data = await resp.json();

        if (!data.nodes) {
            document.getElementById('overlayText').textContent = 'No graph data. Ingest some conversations first.';
            document.getElementById('graphOverlay').classList.remove('hidden');
            return;
        }

        graphData = data;

        // Track diffs — what nodes/edges were added or removed
        const currentNodeIds = new Set(data.nodes.map(n => n.id));
        const currentEdgeIds = new Set(data.edges.map(e => e.id));
        newNodeIds = new Set([...currentNodeIds].filter(id => !previousNodeIds.has(id)));
        removedNodeIds = new Set([...previousNodeIds].filter(id => !currentNodeIds.has(id)));
        const newEdgeCount = [...currentEdgeIds].filter(id => !previousEdgeIds.has(id)).length;
        previousNodeIds = currentNodeIds;
        previousEdgeIds = currentEdgeIds;

        // Update hash
        const hashResp2 = await fetch('/api/graph/hash');
        const hashData2 = await hashResp2.json();
        const changed = currentHash !== '' && hashData2.hash !== currentHash;
        currentHash = hashData2.hash;

        renderGraph();
        updateStats();
        updateCharts();
        buildTypeFilters();

        if (changed) {
            let msg = `Graph updated — ${data.nodes.length} nodes, ${data.edges.length} edges`;
            if (newNodeIds.size > 0) msg += ` (+${newNodeIds.size} new nodes)`;
            if (removedNodeIds.size > 0) msg += ` (-${removedNodeIds.size} removed)`;
            if (newEdgeCount > 0) msg += ` (+${newEdgeCount} new edges)`;
            log('update', msg);
            flashLiveIndicator();

            // Clear diff highlights after 5 seconds
            setTimeout(() => {
                newNodeIds.clear();
                removedNodeIds.clear();
                renderGraph(); // Re-render without highlights
            }, 5000);
        }

    } catch (err) {
        log('error', `Fetch failed: ${err.message}`);
    }
}


async function loadFileList() {
    try {
        const resp = await fetch('/api/files');
        const files = await resp.json();
        const select = document.getElementById('fileSelect');
        select.innerHTML = '';

        if (files.length === 0) {
            select.innerHTML = '<option value="">No graph files found</option>';
            return;
        }

        files.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f.path;
            opt.textContent = `${f.path} (${f.node_count}N/${f.edge_count}E)`;
            select.appendChild(opt);
        });
    } catch (err) {
        log('error', `Failed to load file list: ${err.message}`);
    }
}


async function switchFile(filePath) {
    try {
        const resp = await fetch(`/api/switch?file=${encodeURIComponent(filePath)}`);
        const data = await resp.json();
        if (data.ok) {
            currentHash = '';
            log('success', `Switched to: ${filePath}`);
            fetchAndRender(true);
        } else {
            log('error', data.error);
        }
    } catch (err) {
        log('error', `Switch failed: ${err.message}`);
    }
}


// ════════════════════════════════════════════════════════════
// Graph Rendering
// ════════════════════════════════════════════════════════════

function renderGraph() {
    const nodes = graphData.nodes || [];
    const edges = graphData.edges || [];

    // Build vis nodes
    const visNodeArr = nodes
        .filter(filterNode)
        .map(n => {
            const conf = n.confidence_score || 1;
            const colors = NODE_COLORS[n.type] || NODE_COLORS.entity;
            const baseSize = NODE_SIZES[n.type] || 20;

            // Scale size by confidence
            const size = baseSize * (0.5 + conf * 0.5);

            // Opacity based on confidence
            const opacity = 0.3 + conf * 0.7;

            // Highlight newly added nodes with a glow
            const isNew = newNodeIds.has(n.id);

            return {
                id: n.id,
                label: isNew ? `✦ ${n.label}` : n.label,
                shape: NODE_SHAPES[n.type] || 'dot',
                size: isNew ? size * 1.4 : size,
                color: {
                    background: isNew ? '#2ea04370' : colors.bg,
                    border: isNew ? '#3fb950' : colors.border,
                    highlight: colors.highlight,
                },
                font: {
                    color: isNew ? '#3fb950' : colors.font,
                },
                opacity: opacity,
                borderWidth: isNew ? 4 : 2,
                shadow: isNew ? {
                    enabled: true,
                    color: '#3fb95060',
                    size: 20,
                    x: 0,
                    y: 0,
                } : undefined,
                title: buildNodeTooltip(n),
                _rawData: n,
            };
        });

    // Build vis edges
    const validNodeIds = new Set(visNodeArr.map(n => n.id));
    const visEdgeArr = edges
        .filter(e => validNodeIds.has(e.source_id) && validNodeIds.has(e.target_id))
        .map(e => {
            const color = EDGE_COLORS[e.type] || '#484f58';
            const conf = e.confidence_score || 1;

            return {
                id: e.id,
                from: e.source_id,
                to: e.target_id,
                label: formatEdgeLabel(e.type),
                color: {
                    color: color,
                    highlight: color,
                    hover: color,
                    opacity: 0.3 + conf * 0.7,
                },
                width: 1 + conf * 1.5,
                title: buildEdgeTooltip(e),
                _rawData: e,
            };
        });

    // Update datasets (vis.js handles diffing)
    visNodes.clear();
    visEdges.clear();
    visNodes.add(visNodeArr);
    visEdges.add(visEdgeArr);

    // Show/hide overlay
    if (visNodeArr.length === 0) {
        document.getElementById('overlayText').textContent = 'No nodes to display. Adjust filters or ingest data.';
        document.getElementById('graphOverlay').classList.remove('hidden');
    } else {
        document.getElementById('graphOverlay').classList.add('hidden');
    }
}


function filterNode(node) {
    // Type filter
    if (!activeTypeFilters.has(node.type)) return false;

    // Confidence filter
    const conf = node.confidence_score || 1;
    if (conf < confMinFilter || conf > confMaxFilter) return false;

    // Search filter
    if (searchQuery && !node.label.toLowerCase().includes(searchQuery)) {
        // Also check attributes
        const attrStr = JSON.stringify(node.attributes || {}).toLowerCase();
        if (!attrStr.includes(searchQuery)) return false;
    }

    return true;
}


function applyFilters() {
    renderGraph();
}


// ════════════════════════════════════════════════════════════
// Neighborhood Explorer (double-click)
// ════════════════════════════════════════════════════════════

function onNetworkDoubleClick(params) {
    if (params.nodes.length === 0) {
        // Double-click on empty space — reset zoom
        network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
        log('info', 'Reset view — showing all nodes');
        return;
    }

    const nodeId = params.nodes[0];
    const node = graphData.nodes.find(n => n.id === nodeId);
    if (!node) return;

    // Find all neighboring node IDs
    const neighborIds = new Set([nodeId]);
    (graphData.edges || []).forEach(e => {
        if (e.source_id === nodeId) neighborIds.add(e.target_id);
        if (e.target_id === nodeId) neighborIds.add(e.source_id);
    });

    // Zoom to neighborhood
    network.fit({
        nodes: [...neighborIds],
        animation: { duration: 500, easingFunction: 'easeInOutQuad' },
    });

    // Highlight the neighborhood
    network.selectNodes([...neighborIds]);

    log('info', `Focused on "${node.label}" neighborhood (${neighborIds.size} nodes)`);
}


// ════════════════════════════════════════════════════════════
// Tooltips
// ════════════════════════════════════════════════════════════

function buildNodeTooltip(node) {
    const conf = (node.confidence_score * 100).toFixed(1);
    const decay = node.decay_rate ? node.decay_rate.toFixed(4) : '—';
    let html = `<b>${escHtml(node.label)}</b><br/>`;
    html += `Type: ${node.type}<br/>`;
    html += `Confidence: ${conf}%<br/>`;
    html += `Decay Rate: ${decay}/day<br/>`;
    html += `ID: ${node.id}`;
    return html;
}


function buildEdgeTooltip(edge) {
    const conf = (edge.confidence_score * 100).toFixed(1);
    let html = `<b>${formatEdgeLabel(edge.type)}</b><br/>`;
    html += `Confidence: ${conf}%<br/>`;
    html += `ID: ${edge.id}`;
    return html;
}


function formatEdgeLabel(type) {
    return type.replace(/_/g, ' ');
}


// ════════════════════════════════════════════════════════════
// Inspector
// ════════════════════════════════════════════════════════════

function onNetworkClick(params) {
    const container = document.getElementById('inspectorContent');

    if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const node = graphData.nodes.find(n => n.id === nodeId);
        if (node) {
            renderNodeInspector(node);
            return;
        }
    }

    if (params.edges.length > 0) {
        const edgeId = params.edges[0];
        const edge = graphData.edges.find(e => e.id === edgeId);
        if (edge) {
            renderEdgeInspector(edge);
            return;
        }
    }

    // Clicked on empty space
    container.innerHTML = '<p class="muted">Click a node or edge to inspect it.</p>';
}


function renderNodeInspector(node) {
    const conf = node.confidence_score || 1;
    const confPct = (conf * 100).toFixed(1);
    const confColor = conf > 0.7 ? '#3fb950' : conf > 0.4 ? '#d29922' : '#f85149';

    let attrsHtml = '';
    const attrs = node.attributes || {};
    if (Object.keys(attrs).length > 0) {
        attrsHtml = Object.entries(attrs)
            .map(([k, v]) => `<div class="inspector-field">
                <div class="field-label">${escHtml(k)}</div>
                <div class="field-value mono">${escHtml(JSON.stringify(v))}</div>
            </div>`).join('');
    } else {
        attrsHtml = '<p class="muted">No attributes</p>';
    }

    document.getElementById('inspectorContent').innerHTML = `
        <div class="inspector-field">
            <div class="field-label">Label</div>
            <div class="field-value" style="font-size: 16px; font-weight: 600;">${escHtml(node.label)}</div>
        </div>
        <div class="inspector-field">
            <div class="field-label">Type</div>
            <div class="field-value"><span class="type-badge ${node.type}">${node.type}</span></div>
        </div>
        <div class="inspector-field">
            <div class="field-label">ID</div>
            <div class="field-value mono">${node.id}</div>
        </div>
        <div class="inspector-field">
            <div class="field-label">Confidence</div>
            <div class="field-value">${confPct}%</div>
            <div class="confidence-bar">
                <div class="confidence-bar-fill" style="width: ${confPct}%; background: ${confColor};"></div>
            </div>
        </div>
        <div class="inspector-field">
            <div class="field-label">Decay Rate</div>
            <div class="field-value mono">${node.decay_rate ?? '—'} /day</div>
        </div>
        <div class="inspector-field">
            <div class="field-label">Created</div>
            <div class="field-value">${formatTime(node.created_at)}</div>
        </div>
        <div class="inspector-field">
            <div class="field-label">Last Reinforced</div>
            <div class="field-value">${formatTime(node.last_reinforced)}</div>
        </div>
        <div class="inspector-field">
            <div class="field-label">Source</div>
            <div class="field-value mono">${escHtml(node.source || '—')}</div>
        </div>
        <div class="inspector-field">
            <div class="field-label">Attributes</div>
            ${attrsHtml}
        </div>
        <div class="inspector-field">
            <div class="field-label">Connected Edges</div>
            <div class="field-value">${countConnectedEdges(node.id)}</div>
        </div>
        <div class="inspector-field" style="margin-top: 8px;">
            <button class="btn" onclick="toggleRawJson('node', '${node.id}')" style="width:100%; font-size:11px;">
                📋 Raw JSON
            </button>
            <pre id="rawJson-${node.id}" style="display:none; margin-top:6px; font-size:10px; background:#0d1117; padding:8px; border-radius:4px; overflow-x:auto; color:#8b949e; max-height:200px; overflow-y:auto;"></pre>
        </div>
    `;
}


function renderEdgeInspector(edge) {
    const conf = edge.confidence_score || 1;
    const confPct = (conf * 100).toFixed(1);
    const confColor = conf > 0.7 ? '#3fb950' : conf > 0.4 ? '#d29922' : '#f85149';

    const sourceNode = graphData.nodes.find(n => n.id === edge.source_id);
    const targetNode = graphData.nodes.find(n => n.id === edge.target_id);

    let attrsHtml = '';
    const attrs = edge.attributes || {};
    if (Object.keys(attrs).length > 0) {
        attrsHtml = Object.entries(attrs)
            .map(([k, v]) => `<div class="inspector-field">
                <div class="field-label">${escHtml(k)}</div>
                <div class="field-value mono">${escHtml(JSON.stringify(v))}</div>
            </div>`).join('');
    } else {
        attrsHtml = '<p class="muted">No attributes</p>';
    }

    document.getElementById('inspectorContent').innerHTML = `
        <div class="inspector-field">
            <div class="field-label">Relationship</div>
            <div class="field-value"><span class="edge-badge">${formatEdgeLabel(edge.type)}</span></div>
        </div>
        <div class="inspector-field">
            <div class="field-label">From</div>
            <div class="field-value">${escHtml(sourceNode?.label || edge.source_id)}
                ${sourceNode ? `<span class="type-badge ${sourceNode.type}" style="margin-left:6px;">${sourceNode.type}</span>` : ''}
            </div>
        </div>
        <div class="inspector-field">
            <div class="field-label">To</div>
            <div class="field-value">${escHtml(targetNode?.label || edge.target_id)}
                ${targetNode ? `<span class="type-badge ${targetNode.type}" style="margin-left:6px;">${targetNode.type}</span>` : ''}
            </div>
        </div>
        <div class="inspector-field">
            <div class="field-label">ID</div>
            <div class="field-value mono">${edge.id}</div>
        </div>
        <div class="inspector-field">
            <div class="field-label">Confidence</div>
            <div class="field-value">${confPct}%</div>
            <div class="confidence-bar">
                <div class="confidence-bar-fill" style="width: ${confPct}%; background: ${confColor};"></div>
            </div>
        </div>
        <div class="inspector-field">
            <div class="field-label">Created</div>
            <div class="field-value">${formatTime(edge.created_at)}</div>
        </div>
        <div class="inspector-field">
            <div class="field-label">Attributes</div>
            ${attrsHtml}
        </div>
    `;
}


function countConnectedEdges(nodeId) {
    return (graphData.edges || []).filter(
        e => e.source_id === nodeId || e.target_id === nodeId
    ).length;
}


// ════════════════════════════════════════════════════════════
// Stats & Charts
// ════════════════════════════════════════════════════════════

function updateStats() {
    const nodes = graphData.nodes || [];
    const edges = graphData.edges || [];

    document.getElementById('statNodes').textContent = nodes.length;
    document.getElementById('statEdges').textContent = edges.length;

    const avgConf = nodes.length > 0
        ? (nodes.reduce((s, n) => s + (n.confidence_score || 1), 0) / nodes.length)
        : 0;
    document.getElementById('statAvgConf').textContent = (avgConf * 100).toFixed(0) + '%';

    const lowConf = nodes.filter(n => (n.confidence_score || 1) < 0.5).length;
    document.getElementById('statLowConf').textContent = lowConf;

    document.getElementById('statTimestamp').textContent = graphData.timestamp
        ? `Last: ${formatTime(graphData.timestamp)}`
        : '';
}


function updateCharts() {
    const nodes = graphData.nodes || [];

    // Type distribution
    const typeCounts = {};
    const typeColors = {
        entity: '#58a6ff',
        concept: '#bc8cff',
        event: '#d29922',
        preference: '#3fb950',
        goal: '#f85149',
    };

    nodes.forEach(n => {
        typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
    });

    typeChart.data.labels = Object.keys(typeCounts);
    typeChart.data.datasets[0].data = Object.values(typeCounts);
    typeChart.data.datasets[0].backgroundColor = Object.keys(typeCounts).map(t => typeColors[t] || '#484f58');
    typeChart.update('none');

    // Confidence histogram
    const buckets = [0, 0, 0, 0, 0]; // 0-20, 20-40, 40-60, 60-80, 80-100
    nodes.forEach(n => {
        const conf = n.confidence_score || 1;
        const idx = Math.min(Math.floor(conf * 5), 4);
        buckets[idx]++;
    });
    confChart.data.datasets[0].data = buckets;
    confChart.update('none');
}


function buildTypeFilters() {
    const container = document.getElementById('nodeTypeFilters');
    const types = ['entity', 'concept', 'event', 'preference', 'goal'];
    const counts = {};

    (graphData.nodes || []).forEach(n => {
        counts[n.type] = (counts[n.type] || 0) + 1;
    });

    container.innerHTML = types.map(t => `
        <label class="filter-checkbox">
            <input type="checkbox" data-type="${t}" ${activeTypeFilters.has(t) ? 'checked' : ''} />
            <span class="type-dot ${t}"></span>
            ${t} <span style="color: var(--text-muted); margin-left: auto;">${counts[t] || 0}</span>
        </label>
    `).join('');

    container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const type = e.target.dataset.type;
            if (e.target.checked) {
                activeTypeFilters.add(type);
            } else {
                activeTypeFilters.delete(type);
            }
            applyFilters();
        });
    });
}


// ════════════════════════════════════════════════════════════
// Live Updates — SSE with polling fallback
// ════════════════════════════════════════════════════════════

function startLiveUpdates() {
    // Try SSE first, fall back to polling
    if (typeof EventSource !== 'undefined') {
        connectSSE();
    } else {
        startPolling();
    }
}


function connectSSE() {
    if (eventSource) {
        eventSource.close();
    }

    try {
        eventSource = new EventSource('/api/events');

        eventSource.addEventListener('update', (e) => {
            try {
                const data = JSON.parse(e.data);
                log('update', `SSE: graph changed (${data.node_count}N/${data.edge_count}E)`);
                fetchAndRender(true);
                flashLiveIndicator();
            } catch (err) {
                log('warn', `SSE parse error: ${err.message}`);
            }
        });

        eventSource.onopen = () => {
            log('success', 'SSE connected — live push updates active');
            // Stop polling if running
            if (pollTimer) {
                clearInterval(pollTimer);
                pollTimer = null;
            }
        };

        eventSource.onerror = () => {
            log('warn', 'SSE disconnected — falling back to polling');
            eventSource.close();
            eventSource = null;
            startPolling();
        };
    } catch {
        log('warn', 'SSE not available — using polling');
        startPolling();
    }
}


function startPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
    if (pollInterval > 0) {
        pollTimer = setInterval(() => fetchAndRender(), pollInterval);
    }
}


function flashLiveIndicator() {
    const dot = document.querySelector('.live-dot');
    if (dot) {
        dot.style.background = '#fff';
        setTimeout(() => { dot.style.background = ''; }, 300);
    }
}


// ════════════════════════════════════════════════════════════
// Event Log
// ════════════════════════════════════════════════════════════

function log(level, message) {
    const logEl = document.getElementById('eventLog');
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const entry = document.createElement('div');
    entry.className = `log-entry ${level}`;
    entry.innerHTML = `<span class="log-time">${time}</span>${escHtml(message)}`;
    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;

    // Keep max 100 entries
    while (logEl.children.length > 100) {
        logEl.removeChild(logEl.firstChild);
    }
}


// ════════════════════════════════════════════════════════════
// Utilities
// ════════════════════════════════════════════════════════════

function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}


function formatTime(isoStr) {
    if (!isoStr) return '—';
    try {
        const d = new Date(isoStr);
        return d.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
        });
    } catch {
        return isoStr;
    }
}


// ════════════════════════════════════════════════════════════
// Keyboard Shortcuts
// ════════════════════════════════════════════════════════════

document.addEventListener('keydown', (e) => {
    // Don't trigger shortcuts when typing in inputs
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

    switch (e.key) {
        case 'r':
        case 'R':
            fetchAndRender(true);
            log('info', 'Manual refresh (R)');
            break;
        case 'f':
        case 'F':
            network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
            break;
        case 'e':
        case 'E':
            openExportModal();
            break;
        case '/':
            e.preventDefault();
            document.getElementById('searchInput').focus();
            break;
        case 'Escape':
            // Close export modal if open, otherwise clear selection
            const exportModal = document.getElementById('exportModal');
            if (exportModal && exportModal.style.display !== 'none') {
                closeExportModal();
            } else {
                document.getElementById('searchInput').blur();
                network.unselectAll();
            }
            break;
        case '?':
            showKeyboardHelp();
            break;
    }
});


function showKeyboardHelp() {
    const existing = document.getElementById('helpModal');
    if (existing) { existing.remove(); return; }

    const modal = document.createElement('div');
    modal.id = 'helpModal';
    modal.style.cssText = `
        position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
        background: #21262d; border: 1px solid #30363d; border-radius: 8px;
        padding: 24px; z-index: 1000; min-width: 320px; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    `;
    modal.innerHTML = `
        <h3 style="margin-bottom: 12px; color: #e6edf3;">⌨️ Keyboard Shortcuts</h3>
        <table style="font-size: 13px; color: #8b949e; width: 100%;">
            <tr><td style="padding: 4px 12px 4px 0;"><kbd style="background:#161b22;padding:2px 6px;border-radius:3px;border:1px solid #30363d;">R</kbd></td><td>Refresh graph</td></tr>
            <tr><td style="padding: 4px 12px 4px 0;"><kbd style="background:#161b22;padding:2px 6px;border-radius:3px;border:1px solid #30363d;">F</kbd></td><td>Fit to view</td></tr>
            <tr><td style="padding: 4px 12px 4px 0;"><kbd style="background:#161b22;padding:2px 6px;border-radius:3px;border:1px solid #30363d;">E</kbd></td><td>Export for LaTeX</td></tr>
            <tr><td style="padding: 4px 12px 4px 0;"><kbd style="background:#161b22;padding:2px 6px;border-radius:3px;border:1px solid #30363d;">/</kbd></td><td>Focus search</td></tr>
            <tr><td style="padding: 4px 12px 4px 0;"><kbd style="background:#161b22;padding:2px 6px;border-radius:3px;border:1px solid #30363d;">Esc</kbd></td><td>Clear selection</td></tr>
            <tr><td style="padding: 4px 12px 4px 0;"><kbd style="background:#161b22;padding:2px 6px;border-radius:3px;border:1px solid #30363d;">?</kbd></td><td>Toggle this help</td></tr>
        </table>
        <p style="margin-top: 12px; font-size: 11px; color: #484f58;">
            Double-click a node to explore its neighborhood.<br/>
            Double-click empty space to reset zoom.
        </p>
    `;
    modal.addEventListener('click', () => modal.remove());
    document.body.appendChild(modal);
}


// Toggle raw JSON display for node or edge
function toggleRawJson(type, id) {
    const el = document.getElementById(`rawJson-${id}`);
    if (!el) return;
    if (el.style.display === 'none') {
        const items = type === 'node' ? graphData.nodes : graphData.edges;
        const item = items.find(i => i.id === id);
        el.textContent = JSON.stringify(item, null, 2);
        el.style.display = 'block';
    } else {
        el.style.display = 'none';
    }
}
// Make it globally accessible
window.toggleRawJson = toggleRawJson;


// ════════════════════════════════════════════════════════════
// Export Modal — LaTeX / DOT / CSV / PNG / SVG
// ════════════════════════════════════════════════════════════

let _exportCache = { content: '', filename: '', format: '' };

function openExportModal() {
    const modal = document.getElementById('exportModal');
    modal.style.display = 'flex';
    // Wire up format option clicks
    document.querySelectorAll('.export-format-option').forEach(opt => {
        opt.onclick = () => selectExportFormat(opt.dataset.format);
    });
    // Wire up option changes to auto-refresh preview
    ['optLayout', 'optScale', 'optConfidence', 'optEdgeLabels', 'optPaperMode', 'optMonochrome'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.onchange = () => {
            const current = document.querySelector('.export-format-option.selected');
            if (current) selectExportFormat(current.dataset.format);
        };
    });
    // Click overlay to close
    modal.onclick = (e) => { if (e.target === modal) closeExportModal(); };
    // Generate initial preview
    selectExportFormat('tikz');
    log('info', 'Export modal opened');
}
window.openExportModal = openExportModal;

function closeExportModal() {
    document.getElementById('exportModal').style.display = 'none';
}
window.closeExportModal = closeExportModal;

function selectExportFormat(fmt) {
    // Update selection UI
    document.querySelectorAll('.export-format-option').forEach(opt => {
        opt.classList.toggle('selected', opt.dataset.format === fmt);
        const radio = opt.querySelector('input[type="radio"]');
        if (radio) radio.checked = opt.dataset.format === fmt;
    });

    // Show/hide options panel based on format
    const optionsPanel = document.getElementById('exportOptions');
    const monoRow = document.getElementById('optMonochromeRow');
    if (fmt === 'tikz') {
        optionsPanel.style.display = 'block';
        monoRow.style.display = 'none';
    } else if (fmt === 'dot') {
        optionsPanel.style.display = 'block';
        monoRow.style.display = 'flex';
    } else {
        optionsPanel.style.display = 'none';
    }

    // Handle client-side exports
    if (fmt === 'png' || fmt === 'svg') {
        generateClientExport(fmt);
        return;
    }

    // Server-side export with preview
    generateServerExport(fmt);
}

async function generateServerExport(fmt) {
    const codeEl = document.getElementById('exportCode');
    codeEl.textContent = 'Generating...';

    const params = new URLSearchParams({ format: fmt, preview: 'true' });

    // Add options for TikZ and DOT
    if (fmt === 'tikz' || fmt === 'dot') {
        params.set('layout', document.getElementById('optLayout').value);
        params.set('scale', document.getElementById('optScale').value);
        params.set('show_confidence', document.getElementById('optConfidence').checked);
        params.set('show_edge_labels', document.getElementById('optEdgeLabels').checked);
        params.set('paper_mode', document.getElementById('optPaperMode').checked);
    }
    if (fmt === 'dot') {
        params.set('monochrome', document.getElementById('optMonochrome').checked);
    }

    try {
        const resp = await fetch(`/api/export?${params}`);
        const data = await resp.json();
        if (data.error) {
            codeEl.textContent = `Error: ${data.error}`;
            return;
        }

        _exportCache = { content: data.content, filename: data.filename, format: fmt };
        codeEl.textContent = data.content;

        document.getElementById('exportFilename').textContent = data.filename;
        const bytes = new Blob([data.content]).size;
        document.getElementById('exportSize').textContent = formatBytes(bytes);
    } catch (err) {
        codeEl.textContent = `Error: ${err.message}`;
    }
}

function generateClientExport(fmt) {
    const codeEl = document.getElementById('exportCode');
    const previewEl = document.querySelector('.preview-content');

    if (fmt === 'png') {
        codeEl.textContent = '';
        // Use vis-network canvas export
        const canvas = document.querySelector('#graphCanvas canvas');
        if (!canvas) {
            codeEl.textContent = 'Error: No graph canvas found. Render a graph first.';
            return;
        }
        // Create high-res export (2x)
        const scale = 2;
        const exportCanvas = document.createElement('canvas');
        exportCanvas.width = canvas.width * scale;
        exportCanvas.height = canvas.height * scale;
        const ctx = exportCanvas.getContext('2d');
        ctx.scale(scale, scale);
        // Fill background
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(canvas, 0, 0);

        const dataUrl = exportCanvas.toDataURL('image/png');
        _exportCache = { content: dataUrl, filename: 'dagestan_graph.png', format: 'png' };

        // Show preview as image
        const img = document.createElement('img');
        img.src = dataUrl;
        img.style.cssText = 'max-width:100%;max-height:100%;display:block;margin:8px auto;';
        const pre = previewEl.querySelector('pre');
        if (pre) pre.style.display = 'none';
        // Remove old image preview if any
        const oldImg = previewEl.querySelector('img');
        if (oldImg) oldImg.remove();
        previewEl.appendChild(img);

        document.getElementById('exportFilename').textContent = 'dagestan_graph.png';
        document.getElementById('exportSize').textContent = formatBytes(dataUrl.length * 0.75);
    } else if (fmt === 'svg') {
        // vis-network doesn't have native SVG export, so we generate one from the data
        const svgContent = generateSVGExport();
        _exportCache = { content: svgContent, filename: 'dagestan_graph.svg', format: 'svg' };
        codeEl.textContent = svgContent;
        // Restore pre visibility if hidden by PNG
        const pre = previewEl.querySelector('pre');
        if (pre) pre.style.display = '';
        const oldImg = previewEl.querySelector('img');
        if (oldImg) oldImg.remove();

        document.getElementById('exportFilename').textContent = 'dagestan_graph.svg';
        document.getElementById('exportSize').textContent = formatBytes(new Blob([svgContent]).size);
    }
}

function generateSVGExport() {
    // Build an SVG representation from the current vis-network positions
    const positions = network.getPositions();
    const width = 800, height = 600;

    // Compute bounds
    const nodeIds = Object.keys(positions);
    if (nodeIds.length === 0) return '<svg xmlns="http://www.w3.org/2000/svg"><text>No nodes</text></svg>';

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodeIds.forEach(id => {
        const p = positions[id];
        if (p.x < minX) minX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.x > maxX) maxX = p.x;
        if (p.y > maxY) maxY = p.y;
    });

    const pad = 60;
    const rangeX = (maxX - minX) || 1;
    const rangeY = (maxY - minY) || 1;
    const scaleX = (width - 2 * pad) / rangeX;
    const scaleY = (height - 2 * pad) / rangeY;
    const scale = Math.min(scaleX, scaleY);

    function tx(x) { return pad + (x - minX) * scale; }
    function ty(y) { return pad + (y - minY) * scale; }

    const svgColors = {
        entity: '#58a6ff', concept: '#bc8cff', event: '#d29922',
        preference: '#3fb950', goal: '#f85149'
    };

    let lines = [];
    lines.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`);
    lines.push(`  <rect width="${width}" height="${height}" fill="#0d1117"/>`);
    lines.push(`  <defs><marker id="arrow" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto"><path d="M0,0 L10,3 L0,6 Z" fill="#484f58"/></marker></defs>`);

    // Build id -> node lookup
    const nodeMap = {};
    graphData.nodes.forEach(n => { nodeMap[n.id] = n; });

    // Edges
    graphData.edges.forEach(e => {
        const sp = positions[e.source_id], tp = positions[e.target_id];
        if (!sp || !tp) return;
        const x1 = tx(sp.x), y1 = ty(sp.y), x2 = tx(tp.x), y2 = ty(tp.y);
        const color = EDGE_COLORS[e.edge_type] || '#484f58';
        lines.push(`  <line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${color}" stroke-width="1.5" stroke-opacity="0.6" marker-end="url(#arrow)"/>`);
    });

    // Nodes
    nodeIds.forEach(id => {
        const p = positions[id];
        const node = nodeMap[id];
        if (!node) return;
        const cx = tx(p.x), cy = ty(p.y);
        const color = svgColors[node.node_type] || '#58a6ff';
        const r = 12;
        lines.push(`  <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r}" fill="${color}" fill-opacity="0.3" stroke="${color}" stroke-width="2"/>`);
        // Escape label for XML
        const label = (node.name || node.id).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        lines.push(`  <text x="${cx.toFixed(1)}" y="${(cy + r + 14).toFixed(1)}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="10" fill="#e6edf3">${label}</text>`);
    });

    lines.push('</svg>');
    return lines.join('\n');
}

async function copyExport() {
    if (!_exportCache.content) return;
    try {
        await navigator.clipboard.writeText(_exportCache.content);
        showToast('Copied to clipboard!');
    } catch {
        // Fallback for older browsers
        const ta = document.createElement('textarea');
        ta.value = _exportCache.content;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        showToast('Copied to clipboard!');
    }
}
window.copyExport = copyExport;

function downloadExport() {
    if (!_exportCache.content) return;
    const { content, filename, format } = _exportCache;

    if (format === 'png') {
        // Data URL download
        const a = document.createElement('a');
        a.href = content;
        a.download = filename;
        a.click();
    } else {
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }
    showToast(`Downloaded ${filename}`);
}
window.downloadExport = downloadExport;

function showToast(msg) {
    const t = document.createElement('div');
    t.className = 'copy-toast';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2000);
}

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
}

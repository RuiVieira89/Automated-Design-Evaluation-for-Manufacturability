const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, LevelFormat,
  BorderStyle, WidthType, ShadingType, VerticalAlign,
  PageBreak, TabStopType, TabStopPosition, PageNumberElement, PageNumberType
} = require('docx');
const fs = require('fs');

const BLUE       = "1B4F8A";
const BLUE_LIGHT = "D6E4F0";
const BLUE_MID   = "2E75B6";
const GRAY_LIGHT  = "F5F5F5";
const GRAY_BORDER = "CCCCCC";
const WHITE      = "FFFFFF";
const BLACK      = "000000";

const border = { style: BorderStyle.SINGLE, size: 1, color: GRAY_BORDER };
const borders = { top: border, bottom: border, left: border, right: border };
const noBorder = { style: BorderStyle.NONE, size: 0, color: WHITE };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 120 },
    children: [new TextRun({ text, font: "Arial", size: 28, bold: true, color: BLUE })]
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 80 },
    children: [new TextRun({ text, font: "Arial", size: 24, bold: true, color: BLUE_MID })]
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 60 },
    children: [new TextRun({ text, font: "Arial", size: 22, bold: true, color: "444444" })]
  });
}

function body(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 60, after: 80 },
    children: [new TextRun({ text, font: "Arial", size: 22, color: BLACK, ...opts })]
  });
}

function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, font: "Arial", size: 22, color: BLACK })]
  });
}

function mixedBullet(runs, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { before: 40, after: 40 },
    children: runs
  });
}

function code(text) {
  return new TextRun({ text, font: "Courier New", size: 20, color: "333333" });
}

function bold(text) {
  return new TextRun({ text, font: "Arial", size: 22, bold: true, color: BLACK });
}

function normal(text) {
  return new TextRun({ text, font: "Arial", size: 22, color: BLACK });
}

function spacer(before = 80) {
  return new Paragraph({ spacing: { before, after: 0 }, children: [new TextRun("")] });
}

function rule() {
  return new Paragraph({
    spacing: { before: 120, after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BLUE_LIGHT } },
    children: [new TextRun("")]
  });
}

function headerCell(text, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: BLUE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      children: [new TextRun({ text, font: "Arial", size: 20, bold: true, color: WHITE })]
    })]
  });
}

function dataCell(text, width, shade = false, opts = {}) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade ? GRAY_LIGHT : WHITE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({
      children: [new TextRun({ text, font: "Arial", size: 20, color: BLACK, ...opts })]
    })]
  });
}

function dataCellRuns(runs, width, shade = false) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade ? GRAY_LIGHT : WHITE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: runs })]
  });
}

// ─── Layer stack summary table ─────────────────────────────────────────────
const layerTable = new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [1400, 2200, 2400, 3360],
  rows: [
    new TableRow({ children: [
      headerCell("Layer", 1400), headerCell("Name", 2200),
      headerCell("Primary libs", 2400), headerCell("Responsibility", 3360)
    ]}),
    ...[
      ["L1", "CAD I/O", "pythonocc-core, ifcOpenShell, meshio", "Read STEP/IGES/IFC/mesh formats; emit unified B-Rep or mesh objects"],
      ["L2", "Geometry Kernel", "OCCT, CGAL, trimesh, Open3D, libigl", "Topology queries, mesh repair, curvature, wall thickness, sharp features"],
      ["L3", "Rule Engine", "Python modules + OCC/CGAL, networkx, scipy", "DfX checks, feature dependency DAG, tolerance-stack constraint solving"],
      ["L4", "ML Reasoning", "PyTorch Geometric, PointNet++, ONNX Runtime", "Process-aware classification, feature recognition, confidence scoring"],
      ["L5", "Visualization", "PyVista/VTK, FreeCAD plugin API, Gradio/Streamlit", "Annotated 3D feedback, web UI, headless JSON/screenshot export"],
      ["L6", "Orchestration", "FastAPI, Celery + Redis, Prefect/Airflow", "REST API, async job queuing, batch assembly orchestration"],
    ].map(([layer, name, libs, resp], i) =>
      new TableRow({ children: [
        dataCell(layer, 1400, i % 2 === 0, { bold: true, color: BLUE }),
        dataCell(name, 2200, i % 2 === 0, { bold: true }),
        dataCellRuns([code(libs)], 2400, i % 2 === 0),
        dataCell(resp, 3360, i % 2 === 0),
      ]})
    )
  ]
});

// ─── Dependency table ──────────────────────────────────────────────────────
function depTable(rows) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2200, 1400, 5760],
    rows: [
      new TableRow({ children: [
        headerCell("Package", 2200), headerCell("Version", 1400), headerCell("Purpose", 5760)
      ]}),
      ...rows.map(([pkg, ver, purpose], i) =>
        new TableRow({ children: [
          dataCellRuns([code(pkg)], 2200, i % 2 === 0),
          dataCell(ver, 1400, i % 2 === 0),
          dataCell(purpose, 5760, i % 2 === 0),
        ]})
      )
    ]
  });
}

// ─── API endpoint table ────────────────────────────────────────────────────
const apiTable = new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [1200, 1800, 2000, 4360],
  rows: [
    new TableRow({ children: [
      headerCell("Method", 1200), headerCell("Path", 1800),
      headerCell("Auth", 2000), headerCell("Description", 4360)
    ]}),
    ...[
      ["POST", "/analyse", "API key", "Submit a geometry file (STEP/IGES/IFC) for analysis. Returns job_id immediately (202 Accepted)."],
      ["GET", "/job/{id}", "API key", "Poll job status and retrieve results. States: PENDING, RUNNING, SUCCESS, FAILURE, RETRY."],
      ["GET", "/job/{id}/report", "API key", "Download the structured JSON report for a completed job."],
      ["GET", "/job/{id}/screenshot", "API key", "Download annotated PNG screenshot(s) for a completed job."],
      ["POST", "/feedback", "API key", "Submit designer override or false-positive annotation; routes to L4 retraining store."],
      ["GET", "/health", "None", "Liveness check. Returns 200 OK if the API and Redis are reachable."],
    ].map(([method, path, auth, desc], i) =>
      new TableRow({ children: [
        dataCell(method, 1200, i % 2 === 0, { bold: true, color: BLUE_MID }),
        dataCellRuns([code(path)], 1800, i % 2 === 0),
        dataCell(auth, 2000, i % 2 === 0),
        dataCell(desc, 4360, i % 2 === 0),
      ]})
    )
  ]
});

// ─── Job state table ───────────────────────────────────────────────────────
const stateTable = new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [1600, 3880, 3880],
  rows: [
    new TableRow({ children: [
      headerCell("State", 1600), headerCell("Meaning", 3880), headerCell("Next state(s)", 3880)
    ]}),
    ...[
      ["PENDING", "Job accepted and queued in Redis; no worker has claimed it yet.", "RUNNING"],
      ["RUNNING", "A Celery worker has claimed the task and is executing the L1–L5 pipeline.", "SUCCESS, FAILURE"],
      ["SUCCESS", "Pipeline completed; results written to Redis result backend.", "—"],
      ["FAILURE", "Pipeline raised an unrecoverable exception after all retries exhausted.", "—"],
      ["RETRY", "Transient failure detected; job re-queued for another attempt.", "PENDING"],
    ].map(([state, meaning, next], i) =>
      new TableRow({ children: [
        dataCell(state, 1600, i % 2 === 0, { bold: true }),
        dataCell(meaning, 3880, i % 2 === 0),
        dataCell(next, 3880, i % 2 === 0),
      ]})
    )
  ]
});

// ─── DfX checks table ─────────────────────────────────────────────────────
const dfxTable = new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [2400, 2200, 4760],
  rows: [
    new TableRow({ children: [
      headerCell("Check", 2400), headerCell("Kernel call", 2200), headerCell("Failure condition", 4760)
    ]}),
    ...[
      ["Min wall thickness", "trimesh ray cast + CGAL offset", "Any wall below threshold (default 1.5 mm; configurable per process profile)"],
      ["Draft angles", "OCCT BRep_Tool face normals", "Face normal angle vs. pull direction below minimum (default 1°)"],
      ["Undercut detection", "OCCT silhouette + ray test", "Feature not visible from any valid tool approach direction"],
      ["Hole depth/dia ratio", "OCCT cylindrical face topology", "Depth exceeds 10× diameter for standard tooling"],
      ["Tool access cones", "PyVista visibility + clearance rays", "No valid tool approach cone with required clearance angle"],
    ].map(([check, kernel, fail], i) =>
      new TableRow({ children: [
        dataCell(check, 2400, i % 2 === 0, { bold: true }),
        dataCellRuns([code(kernel)], 2200, i % 2 === 0),
        dataCell(fail, 4760, i % 2 === 0),
      ]})
    )
  ]
});

// ─── Non-functional requirements table ────────────────────────────────────
const nfrTable = new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [2000, 2800, 4560],
  rows: [
    new TableRow({ children: [
      headerCell("Category", 2000), headerCell("Target", 2800), headerCell("Notes", 4560)
    ]}),
    ...[
      ["Interactive latency", "< 3 s for single parts", "FreeCAD plugin and web UI blocking path; measured at P95"],
      ["Batch throughput", "> 50 parts/hour per worker", "Celery worker with 8 CPU cores and 32 GB RAM"],
      ["ML inference latency", "< 200 ms per part", "ONNX Runtime CPU session; GPU session target < 50 ms"],
      ["API availability", "99.5% uptime", "FastAPI + Redis; excludes scheduled maintenance windows"],
      ["Result TTL", "72 hours", "Redis result backend; configurable via RESULT_TTL_SECONDS env var"],
      ["Max geometry file size", "500 MB", "Enforced at FastAPI upload endpoint; configurable"],
      ["Concurrent jobs", "Configurable worker pool", "Default: 4 workers × 4 concurrency = 16 concurrent tasks"],
      ["Model confidence threshold", "≥ 0.65 for ML output", "Below threshold: fall back to L3 deterministic rule result"],
    ].map(([cat, target, notes], i) =>
      new TableRow({ children: [
        dataCell(cat, 2000, i % 2 === 0, { bold: true }),
        dataCell(target, 2800, i % 2 === 0),
        dataCell(notes, 4560, i % 2 === 0),
      ]})
    )
  ]
});

// ─── Document ──────────────────────────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
          { level: 1, format: LevelFormat.BULLET, text: "\u25E6", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 1080, hanging: 360 } } } },
        ]
      }
    ]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: BLUE_MID },
        paragraph: { spacing: { before: 280, after: 80 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: "Arial", color: "444444" },
        paragraph: { spacing: { before: 200, after: 60 }, outlineLevel: 2 } },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BLUE_LIGHT } },
          spacing: { before: 0, after: 120 },
          children: [
            new TextRun({ text: "CAD DfX Analysis Pipeline  ", font: "Arial", size: 18, color: "888888" }),
            new TextRun({ text: "Software Requirements Document", font: "Arial", size: 18, bold: true, color: BLUE })
          ]
        })]
      })
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: BLUE_LIGHT } },
          spacing: { before: 120, after: 0 },
          tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
          children: [
            new TextRun({ text: "Confidential — Internal Use Only  ", font: "Arial", size: 18, color: "888888" }),
            new TextRun({ text: "\tPage ", font: "Arial", size: 18, color: "888888" }),
            new PageNumberElement({ type: PageNumberType.CURRENT, font: "Arial", size: 18 }),
          ]
        })]
      })
    },
    children: [

      // ── Cover ──────────────────────────────────────────────────────────
      new Paragraph({
        spacing: { before: 1440, after: 240 },
        children: [new TextRun({ text: "CAD DfX Analysis Pipeline", font: "Arial", size: 56, bold: true, color: BLUE })]
      }),
      new Paragraph({
        spacing: { before: 0, after: 120 },
        children: [new TextRun({ text: "Software Requirements Document", font: "Arial", size: 36, color: BLUE_MID })]
      }),
      new Paragraph({
        spacing: { before: 0, after: 480 },
        children: [new TextRun({ text: "Version 1.0  |  March 2026  |  Draft", font: "Arial", size: 22, color: "888888" })]
      }),
      rule(),

      // ── 1. Introduction ────────────────────────────────────────────────
      h1("1. Introduction"),
      h2("1.1 Purpose"),
      body("This document defines the software requirements for a six-layer Python-based pipeline that performs automated Design for Manufacturability (DfM) and Design for X (DfX) analysis on 3D CAD geometry. It is intended for the engineering team responsible for implementation, integration, and testing."),

      h2("1.2 Scope"),
      body("The system accepts CAD geometry files (STEP, IGES, IFC, STL, OBJ, VTK) and produces:"),
      bullet("Structured DfX check results with pass/warn/fail severity per feature"),
      bullet("Process-aware ML classifications (e.g. 3-axis machinable, requires 5-axis, casting recommended)"),
      bullet("Annotated 3D visualizations with violation overlays and measurement callouts"),
      bullet("A REST API, web UI, FreeCAD plugin, and headless batch mode"),
      spacer(),

      h2("1.3 Definitions"),
      body("B-Rep: Boundary Representation — a solid model defined by its bounding surfaces, edges, and vertices."),
      body("DfX: Design for X, where X is a manufacturing process (machining, casting, moulding, etc.)."),
      body("OCCT: Open CASCADE Technology, the C++ geometry kernel underlying pythonocc-core."),
      body("ONNX: Open Neural Network Exchange format used for framework-agnostic model deployment."),
      body("Celery chord: A Celery primitive that fans tasks out in parallel and calls a callback when all complete."),
      spacer(),

      h2("1.4 System overview"),
      body("The pipeline is structured as six independently deployable layers. Each layer has a well-defined input contract and output contract. Layers 1–4 are pure computation; Layer 5 is presentation; Layer 6 is infrastructure."),
      spacer(),
      layerTable,
      spacer(160),
      rule(),

      // ── 2. Architecture ────────────────────────────────────────────────
      h1("2. Architecture"),
      h2("2.1 Deployment model"),
      body("All layers are Python packages in a monorepo under a single pyproject.toml. The recommended deployment model is Docker Compose for development and Kubernetes for production. Each layer maps to one or more containers:"),
      bullet("api — FastAPI application server (Layer 6)"),
      bullet("worker — Celery worker pool running Layers 1–5 (one or more replicas)"),
      bullet("redis — Redis 7+ instance (broker and result backend)"),
      bullet("scheduler — Prefect agent or Airflow scheduler for batch flows (Layer 6)"),
      bullet("ui — Gradio or Streamlit web application (Layer 5)"),
      spacer(),

      h2("2.2 Data flow"),
      body("A geometry file submitted via the REST API (or FreeCAD plugin) is validated by FastAPI and enqueued as a Celery task. A worker picks up the task and executes the L1 → L5 pipeline sequentially within a single Python process. Results are written to Redis and optionally persisted to object storage (S3-compatible). The client polls GET /job/{id} until state is SUCCESS or FAILURE."),
      body("For multi-component assemblies, a Celery chord fans the analysis out across all components in parallel. A chord callback aggregates per-component results into a unified assembly report."),
      spacer(),

      h2("2.3 Language and runtime"),
      bullet("Python 3.11+ required across all layers"),
      bullet("No JavaScript, Rust, or Go dependencies in the runtime path"),
      bullet("C++ extensions (OCCT, CGAL) accessed exclusively through their Python bindings — never called directly"),
      bullet("ONNX Runtime is the only ML inference dependency; PyTorch and PyG are training-time only"),
      rule(),

      // ── 3. Layer 1 ─────────────────────────────────────────────────────
      h1("3. Layer 1 — CAD I/O"),
      h2("3.1 Responsibility"),
      body("Layer 1 reads all supported CAD and mesh file formats and emits one of two normalised representations to Layer 2: a B-Rep object (for exact geometry) or a normalised mesh (for tessellated/simulation formats)."),

      h2("3.2 Supported input formats"),
      bullet("STEP (.step, .stp) — via pythonocc-core"),
      bullet("IGES (.iges, .igs) — via pythonocc-core"),
      bullet("IFC (.ifc) — via ifcOpenShell"),
      bullet("STL, OBJ, VTK, MSH, XDMF and 40+ mesh formats — via meshio"),

      h2("3.3 Output contracts"),
      mixedBullet([bold("B-Rep path: "), normal("OCC.TopoDS.Shape object. Passed to Layer 2 OCCT/CGAL subsystems.")]),
      mixedBullet([bold("Mesh path: "), normal("meshio.Mesh object with points (N\u00d73 float64) and cells arrays. Passed to Layer 2 mesh subsystems.")]),
      mixedBullet([bold("Tessellation bridge: "), normal("pythonocc-core can tessellate a B-Rep to a mesh at a configurable chord tolerance (default 0.01 mm). This is the only permitted crossing between the two tracks.")]),

      h2("3.4 Dependencies"),
      spacer(40),
      depTable([
        ["pythonocc-core", "7.7+", "Python bindings for OpenCASCADE OCCT; reads STEP, IGES, native B-Rep"],
        ["ifcOpenShell", "0.7+", "IFC/BIM file parser; exposes geometry and semantic metadata"],
        ["meshio", "5.3+", "Universal mesh format converter; emits numpy-backed Mesh objects"],
      ]),
      spacer(120),
      rule(),

      // ── 4. Layer 2 ─────────────────────────────────────────────────────
      h1("4. Layer 2 — Geometry Kernel"),
      h2("4.1 Responsibility"),
      body("Layer 2 performs geometric analysis on the objects emitted by Layer 1. It maintains two parallel tracks — exact B-Rep and tessellated mesh — and does not merge them. Layer 3 queries both tracks independently."),

      h2("4.2 B-Rep track (OCCT + CGAL)"),
      bullet("Topology walking: face, edge, and vertex enumeration via OCC.BRep_Builder and OCC.TopExp_Explorer"),
      bullet("Face classification: planar, cylindrical, conical, spherical, toroidal, B-spline surface"),
      bullet("Curvature computation: principal curvatures per face via OCC.BRepLProp_SLProps"),
      bullet("Boolean operations: union, intersection, cut via OCC.BRepAlgoAPI"),
      bullet("Mesh repair: hole filling, self-intersection removal via CGAL Python bindings (cgal-python)"),
      bullet("Exact arithmetic: all predicate tests use CGAL exact number types; no floating-point conditionals"),

      h2("4.3 Mesh track (trimesh + Open3D + libigl)"),
      bullet("Wall thickness: bidirectional ray casting via trimesh.ray.ray_pyembree"),
      bullet("Accessibility checks: visibility and clearance rays via trimesh.ray"),
      bullet("Volume and mass properties: trimesh.Trimesh.volume, .center_mass"),
      bullet("Point cloud registration: ICP via Open3D o3d.pipelines.registration"),
      bullet("Normal estimation and voxelisation: Open3D"),
      bullet("Sharp feature detection: dihedral angle analysis via igl.sharp_edges"),
      bullet("Curvature tensors and Laplacian: igl.gaussian_curvature, igl.cotmatrix"),
      bullet("UV parameterisation: igl.harmonic"),

      h2("4.4 Cross-track tessellation"),
      body("The B-Rep track may be tessellated to the mesh track at any point using pythonocc-core BRepMesh_IncrementalMesh. The chord tolerance must be set explicitly; the default value is 0.01 mm and is configurable via the TESS_CHORD_TOLERANCE environment variable. Tessellation is lossy — exact surface parametrisation is not preserved."),

      h2("4.5 Dependencies"),
      spacer(40),
      depTable([
        ["pythonocc-core", "7.7+", "OCCT B-Rep kernel (topology, curvature, Boolean ops, tessellation)"],
        ["cgal-python", "5.5+", "CGAL mesh repair, convex hull, Minkowski sums, exact arithmetic"],
        ["trimesh", "4.0+", "Mesh analysis: wall thickness, ray casting, accessibility, watertightness"],
        ["open3d", "0.18+", "Point cloud processing, ICP registration, normal estimation, voxelisation"],
        ["libigl", "2.4+", "Differential geometry: curvature tensors, Laplacian, sharp features, UV maps"],
        ["numpy", "1.26+", "Shared array format between all mesh-track libraries"],
      ]),
      spacer(120),
      rule(),

      // ── 5. Layer 3 ─────────────────────────────────────────────────────
      h1("5. Layer 3 — Rule Engine"),
      h2("5.1 Responsibility"),
      body("Layer 3 applies a configurable set of DfX rules to the geometry produced by Layer 2. It produces a list of CheckResult objects, each carrying a severity (PASS, WARN, FAIL), a numeric measurement, and a reference to the failing geometry entity (face, edge, or feature node)."),

      h2("5.2 DfxCheck interface"),
      body("Every check must subclass DfxCheck and implement the run(shape, params) -> CheckResult interface. Checks are registered by name in a central rule registry. The registry maps string names to class references, enabling the dependency graph (see 5.4) to schedule checks by name without hard-wiring the execution order."),

      h2("5.3 DfX checks"),
      spacer(40),
      dfxTable,
      spacer(160),

      h2("5.4 Feature dependency graph"),
      body("networkx is used to construct a directed acyclic graph (DAG) where each node is a recognized feature (boss, hole, fillet, pocket, slot) and each edge represents a geometric dependency. A topological sort of this graph defines the order in which DfX checks are executed. If a parent feature check fails, dependent feature checks are suppressed to avoid cascading false results."),
      bullet("Graph construction: called once per part after Layer 2 analysis"),
      bullet("Node attributes: feature type, face IDs, bounding box, layer tag from L4"),
      bullet("Edge attributes: dependency type (face-on-face, edge-shared, component-child)"),
      bullet("Execution order: nx.topological_sort(G) applied before check dispatch"),

      h2("5.5 Tolerance stack solver"),
      body("scipy.optimize.minimize is used to solve worst-case tolerance stack-up across an assembly. The objective function is the maximum gap closure across all tolerance chains. Constraint functions are derived from the CheckResult measurements produced by 5.3 (e.g. measured wall = 1.8 mm, threshold = 2.0 mm, margin = \u22120.2 mm becomes a constraint bound). The solver returns a feasibility verdict per assembly."),

      h2("5.6 Param store"),
      body("All thresholds and tolerances are read from a param store (a Pydantic settings class backed by environment variables or a JSON config file). The param store is injected into each DfxCheck at construction time. Swapping a process profile (e.g. injection moulding vs CNC vs casting) is a single config change with no code modification."),

      h2("5.7 Dependencies"),
      spacer(40),
      depTable([
        ["networkx", "3.2+", "Feature dependency DAG construction, topological sort, check scheduling"],
        ["scipy", "1.12+", "Tolerance stack constraint solving via scipy.optimize.minimize"],
        ["pydantic", "2.5+", "Param store schema, CheckResult dataclass, request/response validation"],
      ]),
      spacer(120),
      rule(),

      // ── 6. Layer 4 ─────────────────────────────────────────────────────
      h1("6. Layer 4 — ML / Context-Aware Reasoning"),
      h2("6.1 Responsibility"),
      body("Layer 4 adds process-aware semantic classification to the geometric and rule results from Layers 2 and 3. It outputs per-feature process labels, axis-count requirements, and confidence scores. It maintains a hard boundary between training-time dependencies (PyTorch, PyG) and inference-time dependencies (ONNX Runtime only)."),

      h2("6.2 Training path"),
      h3("6.2.1 PyTorch Geometric (GNN on B-Rep graph)"),
      body("A graph neural network is trained on feature graphs derived from B-Rep topology. The input is a PyG Data object with the following fields:"),
      bullet("x: node feature matrix (N \u00d7 F float32) — one row per face; features include face area, mean curvature, draft angle, and surface type one-hot"),
      bullet("edge_index: connectivity matrix (2 \u00d7 E int64) derived from shared B-Rep edges"),
      bullet("edge_attr: edge feature vector — convexity (concave/convex/tangent), shared edge length, dihedral angle"),
      bullet("y: graph-level process class label (int64)"),
      body("The model architecture is a 4-layer GraphSAGE with global mean pooling and a 3-layer MLP classifier head. Training uses cross-entropy loss with class weighting for imbalanced process distributions."),

      h3("6.2.2 PointNet++ (point cloud feature recognition)"),
      body("A PointNet++ segmentation model is trained on point clouds sampled from the mesh track. Input tensor shape is (B, N, C) where N is the number of points (1024\u20134096, configurable) and C is the number of per-point features:"),
      bullet("xyz coordinates (3)"),
      bullet("surface normal (3)"),
      bullet("mean curvature (1)"),
      bullet("wall thickness estimate (1)"),
      bullet("layer tag from L2 (1, encoded as float)"),
      body("The output is a per-point feature class label. Farthest-point sampling (FPS) is used for downsampling between set abstraction levels."),

      h3("6.2.3 Export"),
      body("Both models are exported to ONNX format using torch.onnx.export with opset version 17. Exported artefacts are stored in the model registry (a versioned directory or S3 prefix). The model registry path is configured via MODEL_REGISTRY_PATH."),

      h2("6.3 Inference path"),
      body("At inference time, only onnxruntime is imported. PyTorch and PyG must not appear in the worker container image. Two InferenceSession wrappers are maintained:"),
      bullet("GNNSession: accepts a serialised graph (adjacency list + feature tensors); wraps the PyG-exported ONNX model"),
      bullet("PointNetSession: accepts a (1, N, C) float32 tensor; wraps the PointNet++-exported ONNX model"),
      body("When model confidence falls below the ML_CONFIDENCE_THRESHOLD (default 0.65), the inference result is discarded and the corresponding Layer 3 deterministic result is used instead. This fallback must be logged with reason: low_confidence."),

      h2("6.4 Output contract"),
      body("Layer 4 emits a list of FeatureLabel objects, each containing: feature_id, process_class (string), axis_count (int), confidence (float 0\u20131), source (ml or rule_fallback)."),

      h2("6.5 Dependencies"),
      spacer(40),
      depTable([
        ["torch", "2.2+", "Training only — must not appear in worker/inference image"],
        ["torch_geometric", "2.5+", "Training only — GNN model definition and training loop"],
        ["onnxruntime", "1.17+", "Inference only — framework-free ONNX model execution"],
        ["numpy", "1.26+", "Tensor construction for ONNX Runtime input feeds"],
      ]),
      spacer(120),
      rule(),

      // ── 7. Layer 5 ─────────────────────────────────────────────────────
      h1("7. Layer 5 — Visualization & Feedback"),
      h2("7.1 Responsibility"),
      body("Layer 5 presents analysis results to designers through three independent deployment surfaces. A shared annotation engine (PyVista/VTK) produces an annotated 3D scene that each surface renders or exports in its own way."),

      h2("7.2 Annotation engine"),
      body("The annotation engine accepts the Layer 3 CheckResult list and Layer 4 FeatureLabel list and produces an annotated PyVista PolyData object:"),
      bullet("Violation colouring: scalar array attached to each face, values mapped to a diverging colour scale (green = PASS, amber = WARN, red = FAIL)"),
      bullet("Measurement arrows: pyvista.Arrow glyphs placed at violation sites, labelled with measured value and threshold"),
      bullet("Feature labels: 3D text actors positioned at feature centroids, showing process class and confidence"),
      bullet("Scene export: pyvista.Plotter.export_gltf() for web embedding; screenshot() for PNG; save_meshio() for VTK"),

      h2("7.3 FreeCAD plugin"),
      body("A FreeCAD workbench plugin provides in-process analysis within the designer's existing CAD environment."),
      bullet("Entry point: FreeCAD Workbench subclass registered in InitGui.py"),
      bullet("Menu and toolbar: FreeCAD.Gui.addCommand() for Analyse Part, Show Results, Export Report"),
      bullet("3D overlay: annotated scene exported as a Coin3D SoSeparator node tree and inserted as a child of FreeCAD's root scene graph node (provides depth-correct overlay without a separate window)"),
      bullet("Results panel: dockable Qt widget (PySide2/PySide6) showing a sortable table of CheckResult rows"),
      bullet("Pipeline call: the plugin calls the FastAPI REST endpoint synchronously; a progress dialog is shown during the < 3 s blocking call"),

      h2("7.4 Web UI"),
      body("A Gradio or Streamlit application provides a browser-based review interface."),
      bullet("File upload: accepts STEP, IGES, IFC files up to 500 MB; triggers POST /analyse on submit"),
      bullet("Progress indicator: polls GET /job/{id} every 2 s; displays spinner with elapsed time"),
      bullet("3D viewer: embedded pyvista.trame panel or exported glTF in a Three.js viewer component"),
      bullet("Results table: sortable/filterable table of checks with severity badges and clickable face highlight"),
      bullet("Feedback controls: thumbs up/down per check result; free-text override field; submits to POST /feedback"),

      h2("7.5 Headless / API surface"),
      body("The headless surface is used by CI/CD pipelines, batch jobs, and external integrations."),
      bullet("JSON report: structured output conforming to the AnalysisReport Pydantic schema (see Section 9)"),
      bullet("Annotated screenshots: offscreen PyVista render (pyvista.start_xvfb() in headless environments); one PNG per configured camera angle"),
      bullet("REST access: results retrieved via GET /job/{id}/report and GET /job/{id}/screenshot"),

      h2("7.6 Designer feedback loop"),
      body("Each surface must allow designers to mark results as false positives or override process classifications. Feedback payloads are submitted to POST /feedback and written to the retraining store (a versioned JSON Lines file or database table). The store is consumed by the Layer 4 training pipeline as labelled examples."),

      h2("7.7 Dependencies"),
      spacer(40),
      depTable([
        ["pyvista", "0.43+", "3D annotation engine; violation colouring, arrows, scene export"],
        ["vtk", "9.3+", "Underlying VTK backend for PyVista"],
        ["gradio", "4.0+", "Web UI framework (alternative: streamlit 1.30+)"],
        ["trame", "3.0+", "PyVista web embedding for interactive 3D in browser"],
        ["pyside6", "6.6+", "Qt bindings for FreeCAD results panel widget"],
      ]),
      spacer(120),
      rule(),

      // ── 8. Layer 6 ─────────────────────────────────────────────────────
      h1("8. Layer 6 — Orchestration"),
      h2("8.1 Responsibility"),
      body("Layer 6 exposes the pipeline as a production service. It manages the synchronous request surface (FastAPI), the asynchronous execution plane (Celery + Redis), and the batch flow orchestration (Prefect or Airflow)."),

      h2("8.2 FastAPI application"),
      body("The FastAPI application is the sole entry point for all callers (FreeCAD plugin, web UI, CI/CD, external APIs). It never executes pipeline logic directly — it validates requests, enqueues tasks, and returns job handles."),
      spacer(60),
      apiTable,
      spacer(160),
      body("Authentication uses API key validation via the X-API-Key header. Key rotation is supported without restart via environment variable reload. Rate limiting is enforced per API key (configurable; default 100 requests/minute)."),

      h2("8.3 Job state machine"),
      spacer(40),
      stateTable,
      spacer(160),
      body("State transitions are written atomically to Redis. The maximum number of retries is configurable via CELERY_MAX_RETRIES (default 3). Exhausted jobs transition to FAILURE and are written to a dead-letter queue (DLQ) Redis key for operator inspection."),

      h2("8.4 Celery worker"),
      body("The Celery application uses Redis as both broker and result backend. Two broker databases and two result databases are used (separate Redis DB indices) to prevent cross-contamination of task messages and result payloads."),
      bullet("Task: analyse_part(job_id, file_path, params) — executes L1\u2013L5 pipeline; updates job state at start, success, and failure"),
      bullet("Assembly fan-out: chord(analyse_part.s(component) for component in assembly) | aggregate.s() — parallel execution across all components; chord callback writes unified report"),
      bullet("Retry policy: autoretry_for=(GeometryLoadError, OnnxSessionError,), max_retries=3, countdown=10"),
      bullet("Worker concurrency: configured via CELERY_CONCURRENCY (default 4 per worker process)"),
      bullet("Worker memory limit: WORKER_MAX_MEMORY_PER_CHILD=4096 MB — worker process is recycled after limit to prevent OCCT memory leaks"),

      h2("8.5 Batch orchestrator"),
      body("Prefect 2.x (preferred) or Apache Airflow 2.8+ orchestrates multi-step batch flows for large assemblies and scheduled CI runs."),
      bullet("Flow definition: one Prefect flow per assembly analysis; tasks map to Celery task submissions"),
      bullet("Caching: Prefect task result caching keyed on geometry file hash; avoids re-analysing unchanged components"),
      bullet("Schedule: cron triggers (nightly) and webhook triggers (on Git commit to geometry branch)"),
      bullet("Observability: Prefect UI or Airflow DAG view; all flow runs logged to structured JSON"),

      h2("8.6 Redis configuration"),
      bullet("Version: Redis 7.0+"),
      bullet("Broker DB: index 0 (task messages — short-lived, high-throughput)"),
      bullet("Result DB: index 1 (job state and result payloads — TTL managed)"),
      bullet("Result TTL: RESULT_TTL_SECONDS environment variable (default 259200 = 72 hours)"),
      bullet("Persistence: AOF (append-only file) enabled for result DB; RDB snapshot for broker DB"),

      h2("8.7 Dependencies"),
      spacer(40),
      depTable([
        ["fastapi", "0.110+", "REST API framework; async request handling, Pydantic integration"],
        ["uvicorn", "0.29+", "ASGI server for FastAPI"],
        ["celery", "5.3+", "Distributed task queue; worker pool, chord, retry, DLQ"],
        ["redis-py", "5.0+", "Python Redis client for broker and result backend"],
        ["prefect", "2.16+", "Workflow orchestration for batch assembly flows (or airflow 2.8+)"],
        ["flower", "2.0+", "Celery monitoring UI; exposes worker status and task history"],
      ]),
      spacer(120),
      rule(),

      // ── 9. Data schemas ────────────────────────────────────────────────
      h1("9. Data Schemas"),
      h2("9.1 CheckResult"),
      new Paragraph({
        spacing: { before: 80, after: 80 },
        children: [code(
          "class CheckResult(BaseModel):\n" +
          "    check_name: str\n" +
          "    severity: Literal['PASS', 'WARN', 'FAIL']\n" +
          "    measured_value: float\n" +
          "    threshold: float\n" +
          "    unit: str\n" +
          "    feature_id: str\n" +
          "    face_ids: list[int]\n" +
          "    message: str"
        )]
      }),

      h2("9.2 FeatureLabel"),
      new Paragraph({
        spacing: { before: 80, after: 80 },
        children: [code(
          "class FeatureLabel(BaseModel):\n" +
          "    feature_id: str\n" +
          "    process_class: str\n" +
          "    axis_count: int\n" +
          "    confidence: float\n" +
          "    source: Literal['ml', 'rule_fallback']"
        )]
      }),

      h2("9.3 AnalysisReport"),
      new Paragraph({
        spacing: { before: 80, after: 80 },
        children: [code(
          "class AnalysisReport(BaseModel):\n" +
          "    job_id: str\n" +
          "    file_name: str\n" +
          "    file_hash: str\n" +
          "    process_profile: str\n" +
          "    created_at: datetime\n" +
          "    duration_seconds: float\n" +
          "    checks: list[CheckResult]\n" +
          "    features: list[FeatureLabel]\n" +
          "    tolerance_feasible: bool\n" +
          "    assembly_job_ids: list[str]"
        )]
      }),
      rule(),

      // ── 10. Non-functional requirements ───────────────────────────────
      h1("10. Non-Functional Requirements"),
      spacer(40),
      nfrTable,
      spacer(120),
      rule(),

      // ── 11. Environment variables ──────────────────────────────────────
      h1("11. Configuration & Environment Variables"),
      body("All runtime configuration is provided via environment variables. No secrets are committed to source control. A .env.example file is maintained in the repository root."),
      spacer(40),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3200, 2400, 3760],
        rows: [
          new TableRow({ children: [
            headerCell("Variable", 3200), headerCell("Default", 2400), headerCell("Description", 3760)
          ]}),
          ...[
            ["REDIS_URL", "redis://localhost:6379", "Redis connection string for broker and result backend"],
            ["MODEL_REGISTRY_PATH", "./models", "Path or S3 prefix for versioned ONNX model artefacts"],
            ["ML_CONFIDENCE_THRESHOLD", "0.65", "Minimum confidence for ML output; below this, rule fallback is used"],
            ["TESS_CHORD_TOLERANCE", "0.01", "B-Rep tessellation chord tolerance in mm"],
            ["RESULT_TTL_SECONDS", "259200", "Redis result key TTL (default 72 hours)"],
            ["CELERY_CONCURRENCY", "4", "Number of concurrent tasks per Celery worker process"],
            ["CELERY_MAX_RETRIES", "3", "Maximum task retry attempts before FAILURE state"],
            ["WORKER_MAX_MEMORY_PER_CHILD", "4096", "Worker process memory limit in MB before recycling"],
            ["MAX_UPLOAD_SIZE_MB", "500", "Maximum geometry file upload size enforced by FastAPI"],
            ["API_RATE_LIMIT", "100", "Requests per minute per API key"],
            ["XVFB_DISPLAY", ":99", "Xvfb display number for headless PyVista rendering"],
          ].map(([v, d, desc], i) =>
            new TableRow({ children: [
              dataCellRuns([code(v)], 3200, i % 2 === 0),
              dataCellRuns([code(d)], 2400, i % 2 === 0),
              dataCell(desc, 3760, i % 2 === 0),
            ]})
          )
        ]
      }),
      spacer(120),
      rule(),

      // ── 12. Testing ────────────────────────────────────────────────────
      h1("12. Testing Requirements"),
      h2("12.1 Unit tests"),
      bullet("Every DfxCheck subclass must have unit tests covering PASS, WARN, and FAIL cases using synthetic geometry fixtures"),
      bullet("Layer 1 format parsers must be tested against a golden set of reference files (STEP, IGES, IFC, STL)"),
      bullet("Layer 4 ONNX inference wrappers must be tested with known-good input tensors and expected output classes"),
      bullet("Coverage target: 85% line coverage across Layers 1\u20134"),

      h2("12.2 Integration tests"),
      bullet("A full L1\u2013L5 pipeline integration test must run against at least 10 reference parts from the test fixture library"),
      bullet("The FastAPI application must have integration tests for all six endpoints using pytest-asyncio and httpx"),
      bullet("The Celery worker must be integration-tested with a live Redis instance using pytest-celery"),

      h2("12.3 Regression tests (golden set)"),
      bullet("A set of at least 50 reference parts with known DfX check results is maintained in the repository"),
      bullet("The headless REST API surface runs against this golden set in CI on every geometry branch commit"),
      bullet("Any regression in check severity or ML process label triggers a test failure and blocks merge"),

      h2("12.4 Performance tests"),
      bullet("Single-part analysis time must be benchmarked in CI against the 3 s P95 target"),
      bullet("Assembly fan-out with 20 components must complete within 60 s on the standard worker spec"),
      spacer(),
      rule(),

      // ── 13. Out of scope ───────────────────────────────────────────────
      h1("13. Out of Scope"),
      body("The following are explicitly excluded from this release:"),
      bullet("CAD geometry generation or modification (the system is read-only with respect to geometry)"),
      bullet("Cost estimation or supplier quoting (output is manufacturability analysis only)"),
      bullet("Real-time collaborative editing of analysis results"),
      bullet("Native Windows executable packaging (Docker is the supported deployment target)"),
      bullet("Support for proprietary CAD formats (Catia .CATPart, SolidWorks .SLDPRT, etc.) without prior conversion to STEP"),
      spacer(),
      rule(),

      // ── 14. Open questions ─────────────────────────────────────────────
      h1("14. Open Questions"),
      bullet("Should the model registry be a local filesystem path or an S3-compatible object store? Decision needed before Layer 4 implementation begins."),
      bullet("Prefect vs Airflow: team preference and existing infrastructure should drive this choice. Both are acceptable; the interface to Celery is identical."),
      bullet("FreeCAD target version: the workbench API differs between FreeCAD 0.21 and 1.0. Target version must be confirmed before Layer 5 plugin work begins."),
      bullet("Process profile schema: the initial set of process profiles (CNC 3-axis, CNC 5-axis, injection moulding, sand casting, die casting) must be reviewed and signed off by the manufacturing engineering team."),
      spacer(),
      rule(),

      // ── 15. Revision history ───────────────────────────────────────────
      h1("15. Revision History"),
      spacer(40),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1200, 1600, 2560, 4000],
        rows: [
          new TableRow({ children: [
            headerCell("Version", 1200), headerCell("Date", 1600),
            headerCell("Author", 2560), headerCell("Changes", 4000)
          ]}),
          new TableRow({ children: [
            dataCell("1.0", 1200, false),
            dataCell("March 2026", 1600, false),
            dataCell("Engineering Team", 2560, false),
            dataCell("Initial draft covering all six pipeline layers.", 4000, false),
          ]})
        ]
      }),
      spacer(80),
    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("/mnt/user-data/outputs/cad_dfx_pipeline_srd.docx", buf);
  console.log("Done.");
});

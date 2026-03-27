Shape normalization layer.

From TopoDS_Compound:
    enumerate contained shapes
    extract all TopoDS_Solid
    optionally keep parent-child assembly context
    ignore wireframe-only / construction-only geometry unless needed

For each solid:

    enumerate faces
    enumerate edges
    map face IDs
    compute face attributes
    build adjacency via shared edges

Conceptually: 
TopoDS_Compound
  -> TopoDS_CompSolid (optional)
  -> TopoDS_Solid
      -> TopoDS_Shell
          -> TopoDS_Face
              -> TopoDS_Wire
                  -> TopoDS_Edge
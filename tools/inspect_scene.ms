-- Script to inspect CENA_INTERNA_RENDEREASY.max
format "=== INSPECTING SCENE ===\n"
format "Layers in scene:\n"
for i = 0 to (LayerManager.count - 1) do (
    local l = LayerManager.getLayer i
    format "Layer %: '%'\n" i l.name
    local nodes
    l.nodes &nodes
    format "  Node count: %\n" nodes.count
    for n in nodes do (
        format "    - '%'\n" n.name
    )
)

format "\n=== CAMERAS ===\n"
for c in cameras do (
    format "Camera: '%', class: %\n" c.name (classOf c)
)

format "\n=== RENDERER & OVERRIDE ===\n"
format "Current renderer: %\n" (classOf renderers.current)
if isProperty renderers.current #mtlOverride do (
    format "mtlOverride: %\n" renderers.current.mtlOverride
)
if isProperty renderers.current #mtlOverrideEnable do (
    format "mtlOverrideEnable: %\n" renderers.current.mtlOverrideEnable
)

format "\n=== RENDER ELEMENTS ===\n"
re = maxOps.GetCurRenderElementMgr()
format "Render elements count: %\n" (re.NumRenderElements())
for i = 0 to (re.NumRenderElements() - 1) do (
    local elem = re.GetRenderElement i
    format "Elem %: '%', class: %, enabled: %\n" i elem.elementName (classOf elem) elem.enabled
    if (classOf elem == Corona_Masking or classOf elem == CMasking_Mask) do (
        format "  mask type / props:\n"
        show elem
    )
)
format "=== END INSPECT ===\n"

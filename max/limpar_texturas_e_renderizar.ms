-- Script ZYcompose: Remove texturas ausentes, aplica Clay White puro e Renderiza 4K sem interrupcoes
(
    clearListener()
    print "=========================================================="
    print ">>> PREPARANDO CENA: REMOVENDO TEXTURAS E INICIANDO 4K <<<"
    print "=========================================================="
    
    -- 1. DESATIVA POPUPS E MENSAGENS BLOQUEANTES DO 3DS MAX E CORONA
    setSilentMode true
    try (renderers.current.system_vfbShowCoronaWarnings = false) catch ()
    
    local outDir = @"C:\Users\saant\Desktop\compose\renders\sala_estar\"
    makeDir outDir all:true
    
    local r = renderers.current
    local reMgr = maxOps.GetCurRenderElementMgr()
    local cam = getNodeByName "CoronaCamera007"
    
    if cam == undefined do (
        messageBox "Erro: CoronaCamera007 nao encontrada!" title:"ZYcompose"
        return false
    )
    
    -- 2. TRAVA CAMERA E CONFIGURA 4K UHD (3840x2160, 16:9)
    setTransformLockFlags cam #{1..9}
    if cam.target != undefined do setTransformLockFlags cam.target #{1..9}
    cam.enableDof = false
    cam.mblurShutterCurveEnabled = false
    
    r.system_vfbRegions_enabled = false
    renderWidth = 3840
    renderHeight = 2160
    renderPixelAspect = 1.0
    print "Resolucao: 3840x2160 configurada com sucesso."
    
    -- 3. REMOVE TEXTURAS E APLICA MATERIAL OVERRIDE CLAY BRANCO NEUTRO
    for m in scenematerials do (
        try (m.baseTexmap = undefined) catch ()
        try (m.colorDiffuseTexmap = undefined) catch ()
        try (m.texmapDiffuse = undefined) catch ()
        try (m.texmapBump = undefined) catch ()
        try (m.texmapDisplacement = undefined) catch ()
        try (m.texmapOpacity = undefined) catch ()
    )
    
    -- Cria material branco/cinza claro neutro para override via CoronaLegacyMtl
    r.mtlOverride_enabled = true
    local clayMtl = CoronaLegacyMtl()
    clayMtl.name = "ZYcompose_Clay_White"
    clayMtl.colorDiffuse = color 215 215 215
    clayMtl.levelDiffuse = 1.0
    r.mtlOverride = clayMtl
    r.mtlOverride_preserveGlassMtl = false
    r.mtlOverride_preserveBumpMtl = false
    r.mtlOverride_preserveDisplacement = false
    print "Material Override Clay Branco ativo (todas as texturas antigas removidas)."
    
    -- 4. APLICA MODIFICADOR UV_config (CANAL 2, BOX 100x100x100 cm) NA LAYER ANTIGRAVITY
    local lay = LayerManager.getLayerFromName "ANTIGRAVITY"
    if lay != undefined then (
        local nodes = #()
        lay.nodes &nodes
        for n in nodes where (isKindOf n GeometryClass and not (isKindOf n Targetobject)) do (
            local uvMod = undefined
            for m in n.modifiers where m.name == "UV_config" do uvMod = m
            if uvMod == undefined do (
                uvMod = Uvwmap()
                uvMod.name = "UV_config"
                addModifier n uvMod
            )
            uvMod.mapChannel = 2
            uvMod.maptype = 4
            uvMod.length = 100.0
            uvMod.width = 100.0
            uvMod.height = 100.0
            print ("  UV_config (Canal 2) aplicado em: " + n.name)
        )
    )
    
    -- 5. RENDER ELEMENTS PADRONIZADOS
    reMgr.RemoveAllRenderElements()
    
    fn addElem elem name filename = (
        elem.elementName = name
        elem.enabled = true
        elem.filter = true
        reMgr.AddRenderElement elem
        local idx = (reMgr.NumRenderElements() - 1)
        reMgr.SetRenderElementFilename idx filename
        print ("  + [" + (idx as string) + "] Elemento configurado: " + name + " -> " + filename)
    )
    
    local el_dlight = CShading_RawComponent()
    el_dlight.which = 0
    try(el_dlight.useDenoise = false) catch()
    addElem el_dlight "diff_light" (outDir + "cam7_diff_light.exr")
    
    local el_dcol = CShading_SourceColor()
    el_dcol.which = 0
    addElem el_dcol "diff_color" (outDir + "cam7_diff_color.exr")
    
    local el_refl = CShading_Components()
    el_refl.addDirectReflect = true
    el_refl.addIndirectReflect = true
    el_refl.addDirectDiffuse = false
    el_refl.addIndirectDiffuse = false
    el_refl.addDirectRefract = false
    el_refl.addIndirectRefract = false
    el_refl.addDirectTranslucency = false
    el_refl.addIndirectTranslucency = false
    el_refl.addEmission = false
    try(el_refl.useDenoise = true) catch()
    addElem el_refl "reflect" (outDir + "cam7_reflect.exr")
    
    local el_refr = CShading_Components()
    el_refr.addDirectRefract = true
    el_refr.addIndirectRefract = true
    el_refr.addDirectDiffuse = false
    el_refr.addIndirectDiffuse = false
    el_refr.addDirectReflect = false
    el_refr.addIndirectReflect = false
    el_refr.addDirectTranslucency = false
    el_refr.addIndirectTranslucency = false
    el_refr.addEmission = false
    try(el_refr.useDenoise = true) catch()
    addElem el_refr "refract" (outDir + "cam7_refract.exr")
    
    local el_transl = CShading_Components()
    el_transl.addDirectTranslucency = true
    el_transl.addIndirectTranslucency = true
    el_transl.addDirectDiffuse = false
    el_transl.addIndirectDiffuse = false
    el_transl.addDirectReflect = false
    el_transl.addIndirectReflect = false
    el_transl.addDirectRefract = false
    el_transl.addIndirectRefract = false
    el_transl.addEmission = false
    addElem el_transl "transl" (outDir + "cam7_transl.exr")
    
    local el_emiss = CShading_Components()
    el_emiss.addEmission = true
    el_emiss.addDirectDiffuse = false
    el_emiss.addIndirectDiffuse = false
    el_emiss.addDirectReflect = false
    el_emiss.addIndirectReflect = false
    el_emiss.addDirectRefract = false
    el_emiss.addIndirectRefract = false
    el_emiss.addDirectTranslucency = false
    el_emiss.addIndirectTranslucency = false
    addElem el_emiss "emission" (outDir + "cam7_emission.exr")
    
    local el_uv = CGeometry_UvwCoords()
    el_uv.uvwChannel = 2
    addElem el_uv "uv" (outDir + "cam7_uv.exr")
    
    -- MASKS_A: R = PISO, G = SOFA, B = PAREDE
    local el_ma = CMasking_Mask()
    el_ma.mode = 0
    local n_piso = getNodeByName "PISO"
    local n_sofa = getNodeByName "SOFA"
    local n_parede = getNodeByName "PAREDE"
    if n_piso != undefined do ( el_ma.nodesROn = true; el_ma.nodesR = #(n_piso) )
    if n_sofa != undefined do ( el_ma.nodesGOn = true; el_ma.nodesG = #(n_sofa) )
    if n_parede != undefined do ( el_ma.nodesBOn = true; el_ma.nodesB = #(n_parede) )
    addElem el_ma "masks_a" (outDir + "cam7_masks_a.exr")
    
    -- MASKS_B: R = CARPET, G = BANCADA, B = ARMARIOS
    local el_mb = CMasking_Mask()
    el_mb.mode = 0
    local n_carpet = getNodeByName "CARPET"
    local n_bcima = getNodeByName "BANCADA_CIMA"
    local n_bbaixo = getNodeByName "BANCADA_BAIXO"
    local n_abaixo = getNodeByName "ARMARIO_BAIXO"
    local n_acima = getNodeByName "ARMARIO_CIMA"
    if n_carpet != undefined do ( el_mb.nodesROn = true; el_mb.nodesR = #(n_carpet) )
    local g_nodes = #()
    if n_bcima != undefined do append g_nodes n_bcima
    if n_bbaixo != undefined do append g_nodes n_bbaixo
    if g_nodes.count > 0 do ( el_mb.nodesGOn = true; el_mb.nodesG = g_nodes )
    local b_nodes = #()
    if n_abaixo != undefined do append b_nodes n_abaixo
    if n_acima != undefined do append b_nodes n_acima
    if b_nodes.count > 0 do ( el_mb.nodesBOn = true; el_mb.nodesB = b_nodes )
    addElem el_mb "masks_b" (outDir + "cam7_masks_b.exr")
    
    -- MASKS_C: R = CoffeeTables+MESINHA, G = MESA+CADEIRAS, B = COIFA
    local el_mc = CMasking_Mask()
    el_mc.mode = 0
    local r_nodes_c = #()
    local n_ct = getNodeByName "CoffeeTables"
    local n_mesinha = getNodeByName "MESINHA"
    if n_ct != undefined do append r_nodes_c n_ct
    if n_mesinha != undefined do append r_nodes_c n_mesinha
    if r_nodes_c.count > 0 do ( el_mc.nodesROn = true; el_mc.nodesR = r_nodes_c )
    
    local g_nodes_c = #()
    local n_mesa = getNodeByName "MESA"
    local n_mcad = getNodeByName "MESA_CADEIRAS"
    local n_cadb = getNodeByName "CADEIRA_BANCADA"
    if n_mesa != undefined do append g_nodes_c n_mesa
    if n_mcad != undefined do append g_nodes_c n_mcad
    if n_cadb != undefined do append g_nodes_c n_cadb
    if g_nodes_c.count > 0 do ( el_mc.nodesGOn = true; el_mc.nodesG = g_nodes_c )
    
    local n_coifa = getNodeByName "COIFA"
    if n_coifa != undefined do ( el_mc.nodesBOn = true; el_mc.nodesB = #(n_coifa) )
    addElem el_mc "masks_c" (outDir + "cam7_masks_c.exr")
    
    -- LIGHT GROUPS
    local el_lsol = CShading_LightSelect()
    el_lsol.addEnvironment = false
    local n_sun = getNodeByName "Corona Sun001"
    if n_sun != undefined do el_lsol.includedNodes = #(n_sun)
    try(el_lsol.useDenoise = true) catch()
    addElem el_lsol "lg_sol" (outDir + "cam7_lg_sol.exr")
    
    local el_lsky = CShading_LightSelect()
    el_lsky.addEnvironment = true
    el_lsky.includedNodes = #()
    try(el_lsky.useDenoise = true) catch()
    addElem el_lsky "lg_sky" (outDir + "cam7_lg_sky.exr")
    
    -- 6. DISPARA O PIPELINE EM 2 PASSES
    rendSaveFile = true
    rendOutputFilename = outDir + "cam7_beauty.exr"
    
    print "=========================================================="
    print ">>> FASE 1: RENDER 1 - SHADING E LUZ (35 PASSES COM DENOISE)"
    print "=========================================================="
    local count1 = reMgr.NumRenderElements()
    for i = 0 to (count1 - 1) do (
        local elem = reMgr.GetRenderElement i
        if matchPattern elem.elementName pattern:"uv*" or matchPattern elem.elementName pattern:"masks*" then (
            elem.enabled = false
        ) else (
            elem.enabled = true
        )
    )
    r.progressive_passLimit = 35
    r.progressive_timeLimit = 0
    r.adaptivity_targetError = 0.0
    
    render camera:cam frame:0 outputfile:(outDir + "cam7_beauty.exr") vfb:true
    print ">>> RENDER 1 GRAVADO COM SUCESSO! <<<"
    
    print "=========================================================="
    print ">>> FASE 2: RENDER 2 - UVS E MASCARAS (16 PASSES NITIDOS)"
    print "=========================================================="
    local count2 = reMgr.NumRenderElements()
    for i = 0 to (count2 - 1) do (
        local elem = reMgr.GetRenderElement i
        if matchPattern elem.elementName pattern:"uv*" or matchPattern elem.elementName pattern:"masks*" then (
            elem.enabled = true
        ) else (
            elem.enabled = false
        )
    )
    r.progressive_passLimit = 16
    r.progressive_timeLimit = 0
    r.adaptivity_targetError = 0.0
    try (r.image_prefilter_width = 1.0) catch ()
    
    render camera:cam frame:0 outputfile:(outDir + "cam7_beauty_pass2.exr") vfb:true
    print ">>> RENDER 2 GRAVADO COM SUCESSO! <<<"
    
    -- Restaura todos os elementos
    local countFinal = reMgr.NumRenderElements()
    for i = 0 to (countFinal - 1) do (
        local elem = reMgr.GetRenderElement i
        elem.enabled = true
    )
    
    setSilentMode false
    print "=========================================================="
    print ">>> PIPELINE CONCLUIDO! ARQUIVOS GRAVADOS EM: "
    print outDir
    print "=========================================================="
    
    messageBox "Render 4K Concluido com sucesso!\nTodos os arquivos EXR gravados na pasta." title:"ZYcompose"
    "PIPELINE_DONE"
)

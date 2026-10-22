-- Script headless para renderizar apenas os passes de UV e Mascaras em RGB
(
    clearListener()
    print "=========================================================="
    print ">>> CARREGANDO CENA E RENDERIZANDO MASCARAS RGB EM 4K <<<"
    print "=========================================================="
    
    setSilentMode true
    try (renderers.current.system_vfbShowCoronaWarnings = false) catch ()
    
    local outDir = @"C:\Users\saant\Desktop\compose\renders\sala_estar\"
    makeDir outDir all:true
    
    local r = renderers.current
    local reMgr = maxOps.GetCurRenderElementMgr()
    local cam = getNodeByName "CoronaCamera007"
    
    if cam == undefined do (
        print "ERRO: CoronaCamera007 nao encontrada!"
        quitMax #noPrompt
        return false
    )
    
    -- Resolução 4K UHD
    renderWidth = 3840
    renderHeight = 2160
    renderPixelAspect = 1.0
    r.system_vfbRegions_enabled = false
    
    -- Remove todos os render elements e configura apenas UV e Máscaras em RGB
    reMgr.RemoveAllRenderElements()
    
    fn addElem elem name filename = (
        elem.elementName = name
        elem.enabled = true
        elem.filter = true
        reMgr.AddRenderElement elem
        local idx = (reMgr.NumRenderElements() - 1)
        reMgr.SetRenderElementFilename idx filename
        print ("  + Elemento configurado: " + name + " -> " + filename)
    )
    
    -- UV (Canal 2)
    local el_uv = CGeometry_UvwCoords()
    el_uv.uvwChannel = 2
    addElem el_uv "uv" (outDir + "cam7_uv.exr")
    
    -- MASKS_A (mode = 1: RGB): R = PISO, G = SOFA, B = PAREDE
    local el_ma = CMasking_Mask()
    el_ma.mode = 1 -- RGB MODE
    local n_piso = getNodeByName "PISO"
    local n_sofa = getNodeByName "SOFA"
    local n_parede = getNodeByName "PAREDE"
    if n_piso != undefined do ( el_ma.nodesROn = true; el_ma.nodesR = #(n_piso) )
    if n_sofa != undefined do ( el_ma.nodesGOn = true; el_ma.nodesG = #(n_sofa) )
    if n_parede != undefined do ( el_ma.nodesBOn = true; el_ma.nodesB = #(n_parede) )
    addElem el_ma "masks_a" (outDir + "cam7_masks_a.exr")
    
    -- MASKS_B (mode = 1: RGB): R = CARPET, G = BANCADA, B = ARMARIOS
    local el_mb = CMasking_Mask()
    el_mb.mode = 1 -- RGB MODE
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
    
    -- MASKS_C (mode = 1: RGB): R = CoffeeTables+MESINHA, G = MESA+CADEIRAS, B = COIFA
    local el_mc = CMasking_Mask()
    el_mc.mode = 1 -- RGB MODE
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
    
    -- 12 passes são mais do que suficientes para anti-aliasing perfeito das máscaras
    r.progressive_passLimit = 12
    r.progressive_timeLimit = 0
    r.adaptivity_targetError = 0.0
    try (r.image_prefilter_width = 1.0) catch ()
    
    rendSaveFile = true
    rendOutputFilename = outDir + "cam7_beauty_pass2.exr"
    
    print "Iniciando render headless de 12 passes para UV e Mascaras..."
    render camera:cam frame:0 outputfile:(outDir + "cam7_beauty_pass2.exr") vfb:false
    
    print "=========================================================="
    print ">>> MASCARAS RGB E UV GRAVADOS COM SUCESSO EM 4K! <<<"
    print "=========================================================="
    
    -- Salva cena de volta para manter tudo atualizado
    saveMaxFile @"D:\_ASSETS\_SCENES\CENA_INTERNA_RENDEREASY.max" clearNeedSaveFlag:true useNewFile:false
    print "Cena salva com sucesso!"
    
    quitMax #noPrompt
)

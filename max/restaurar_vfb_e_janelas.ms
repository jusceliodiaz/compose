-- Script para restaurar o Corona VFB e reativar a exibicao da janela de render
(
    -- 1. Reativa a exibicao da janela de render (VFB) no 3ds Max
    rendShowVFB = true
    setSilentMode false
    
    -- 2. Restaura configuracoes padrao do Corona VFB
    try (renderers.current.system_vfbShowCoronaWarnings = true) catch ()
    try (renderers.current.system_vfbRegions_enabled = false) catch ()
    
    -- 3. Reseta a posicao da janela do VFB para o centro da sua tela
    try (CoronaRenderer.CoronaFp.resetVfbPosition()) catch ()
    
    -- 4. Forca o Corona VFB a abrir imediatamente
    try (CoronaRenderer.CoronaFp.showVfb()) catch ()
    
    messageBox "Janela de Render (Corona VFB) restaurada com sucesso!" title:"Restaurar VFB"
)

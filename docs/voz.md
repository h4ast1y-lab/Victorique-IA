# Ouvir a Victorique

Abra o aplicativo pelo `run.bat` habitual. Em **Configurações → Voz**, use o player do **Laboratório de voz** para ouvir a demonstração. Para criar outra fala, escreva uma frase, escolha o idioma e a referência e clique em **Gerar áudio**. O primeiro pedido inicializa o modelo e pode levar mais tempo. O player permite pausar e repetir. A opção **Ler as respostas em voz alta** usa o mesmo motor para as respostas seguintes.

Os dez arquivos em `data/voice/references` fornecem a identidade vocal por referência. O rótulo normal é o padrão. O processo usa os pesos de Chatterbox Multilingual em `data/voice/models` e o Python de `.venv-voice`. A síntese roda localmente e preserva a marca d’água do modelo. A fala pode variar entre gerações. Teste frases curtas ao comparar referências.

A aplicação inicia o serviço na porta local 8100 quando há um pedido de síntese. O serviço monitora o processo da aplicação e encerra quando ela fecha. Em caso de falha, consulte `data/voice/service.log`. A demonstração gravada pode ser ouvida independentemente da disponibilidade do motor.

Para voltar temporariamente ao motor anterior, feche a aplicação, renomeie a pasta `.venv-voice` e reabra pelo mesmo iniciador. Para reativar o Chatterbox, restaure o nome e reinicie. As referências e os dados pessoais permanecem em suas pastas.


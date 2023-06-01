import pytesseract
from PIL import Image

# Caminho para o executável do Tesseract OCR
pytesseract.pytesseract.tesseract_cmd = r'./'

# Abrir a imagem
imagem = Image.open('./manuscrito.png')

# Converter a imagem para escala de cinza
imagem_cinza = imagem.convert('L')

# Realizar a transcrição do texto
texto_transcrito = pytesseract.image_to_string(imagem_cinza, lang='por')

# Imprimir o texto transcrito
print(texto_transcrito)

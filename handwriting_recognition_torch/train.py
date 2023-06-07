import os
import tarfile
import pyopencl as cl
from tqdm import tqdm
from io import BytesIO
from zipfile import ZipFile
from urllib.request import urlopen

import torch
import torch.optim as optim
from torchsummaryX import summary

from mltu.torch.model import Model
from mltu.torch.losses import CTCLoss
from mltu.torch.dataProvider import DataProvider
from mltu.torch.metrics import CERMetric, WERMetric
from mltu.torch.callbacks import EarlyStopping, ModelCheckpoint, TensorBoard, Model2onnx, ReduceLROnPlateau

from mltu.preprocessors import ImageReader
from mltu.transformers import ImageResizer, LabelIndexer, LabelPadding, ImageShowCV2
from mltu.augmentors import RandomBrightness, RandomRotate, RandomErodeDilate, RandomSharpen
from mltu.annotations.images import CVImage

from model import Network
from configs import ModelConfigs


dataset_path = "data//iam_data"

dataset, vocab, max_len = [], set(), 0

# Preprocess the dataset by the specific IAM_Words dataset file structure
words = open(f"{dataset_path}//words.txt", "r").readlines()
for line in tqdm(words):
    if line.startswith("#"):
        continue

    line_split = line.split(" ")
    if line_split[1] == "err":
        continue

    folder1 = line_split[0][:3]
    folder2 = "-".join(line_split[0].split("-")[:2])
    file_name = line_split[0] + ".png"
    label = line_split[-1].rstrip("\n")

    rel_path = f"{dataset_path}//words//{folder1}//{folder2}//{file_name}"
    if not os.path.exists(rel_path):
        print(f"File not found: {rel_path}")
        continue

    dataset.append([rel_path, label])
    vocab.update(list(label))
    max_len = max(max_len, len(label))

configs = ModelConfigs()

# Save vocab and maximum text length to configs
configs.vocab = "".join(sorted(vocab))
configs.max_text_length = max_len
configs.save()

# Create a data provider for the dataset
data_provider = DataProvider(
    dataset=dataset,
    skip_validation=True,
    batch_size=configs.batch_size,
    data_preprocessors=[ImageReader(CVImage)],
    transformers=[
        # ImageShowCV2(),  # uncomment to show images when iterating over the data provider
        ImageResizer(configs.width, configs.height, keep_aspect_ratio=False),
        LabelIndexer(configs.vocab),
        LabelPadding(max_word_length=configs.max_text_length,
                     padding_value=len(configs.vocab))
    ],
    use_cache=True,
)

# Divisão do dataset em treino e teste (90% e 10%)
train_dataProvider, test_dataProvider = data_provider.split(split=0.9)

# Argumentação de dados
train_dataProvider.augmentors = [
    RandomBrightness(),
    RandomErodeDilate(),
    RandomSharpen(),
    RandomRotate(angle=10),
]

network = Network(len(configs.vocab), activation="leaky_relu", dropout=0.3)
loss = CTCLoss(blank=len(configs.vocab))
optimizer = optim.Adam(network.parameters(), lr=configs.learning_rate)

# Mostra o sumário do modelo
# summary(network, torch.zeros((1, configs.height, configs.width, 3)))

# Usar GPU
# if torch.cuda.is_available():
#     network = network.cuda()

# Usar CPU
device = torch.device('cpu')
network = network.to(device)
print(torch.__version__)
print(torch.device("cuda" if torch.cuda.is_available() else "cpu"))


# Criação do callback para o treinamento
earlyStopping = EarlyStopping(
    monitor="val_CER", patience=20, mode="min", verbose=1)
modelCheckpoint = ModelCheckpoint(
    configs.model_path + "/model.pt", monitor="val_CER", mode="min", save_best_only=True, verbose=1)
tb_callback = TensorBoard(configs.model_path + "/logs")
reduce_lr = ReduceLROnPlateau(
    monitor="val_CER", factor=0.9, patience=10, verbose=1, mode="min", min_lr=1e-6)
model2onnx = Model2onnx(
    saved_model_path=configs.model_path + "/model.pt",
    input_shape=(1, configs.height, configs.width, 3),
    verbose=1,
    metadata={"vocab": configs.vocab}
)

# Criação do modelo para o treinamento
model = Model(network, optimizer, loss, metrics=[
              CERMetric(configs.vocab), WERMetric(configs.vocab)])
# model.cpu()
model.fit(
    train_dataProvider,
    test_dataProvider,
    epochs=1000,
    callbacks=[earlyStopping, modelCheckpoint,
               tb_callback, reduce_lr, model2onnx]
)

# Save training and validation datasets as csv files
train_dataProvider.to_csv(os.path.join(configs.model_path, "train.csv"))
test_dataProvider.to_csv(os.path.join(configs.model_path, "val.csv"))

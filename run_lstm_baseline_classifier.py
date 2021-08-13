import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import DataLoader
from torchtext.vocab import GloVe,Vocab
from tqdm import tqdm
from utils import IMDB_indexing, pad_sequence
from models import CNN_Baseline,LSTMBaseline
import torchtext.vocab
import csv
import pandas as pd
import argparse
import logging
import os
import pickle
import sys
import config
config.seed_torch()

import time

def epoch_time(start_time, end_time):
    elapsed_time = end_time - start_time
    elapsed_mins = int(elapsed_time / 60)
    elapsed_secs = int(elapsed_time - (elapsed_mins * 60))
    return elapsed_mins, elapsed_secs
def weight_matrix(vocab, vectors, dim=100):
    weight_matrix = np.zeros([len(vocab.itos), dim])
    for i, token in enumerate(vocab.stoi):
        try:
            weight_matrix[i] = vectors.__getitem__(token)
        except KeyError:
            weight_matrix[i] = np.random.normal(scale=0.5, size=(dim,))
    return torch.from_numpy(weight_matrix)
def prepare_dateset(train_data_path, validation_data_path,test_data_path,vocab):
    # with open(train_data_path,'r') as csvfile:
    #     csvreader = csv.reader(csvf
    training_texts = []
    training_labels =[]
    validation_texts = []
    validation_labels = []
    testing_texts = []
    testing_labels = []
    # training #
    print('Start loading training data')
    logging.info("Start loading training data")
    training = pd.read_csv(train_data_path)

    training_review = training.Review[:5]
    training_sentiment = training.Sentiment[:5]

    for text,label in zip(training_review,training_sentiment):
        training_texts.append(text)
        training_labels.append(label)
    print("Finish loading training data")
    logging.info("Finish loading training data")

    # validation #
    print('Start loading validation data')
    logging.info("Start loading validation data")

    validation = pd.read_csv(validation_data_path)
    validation_review = validation.Review
    validation_sentiment = validation.Sentiment


    for text,label in zip(validation_review,validation_sentiment):
        validation_texts.append(text)
        validation_labels.append(label)
    print("Finish loading validation data")
    logging.info("Finish loading validation data")
    # testing #

    print('Start loading testing data')
    logging.info("Start loading testing data")

    testing = pd.read_csv(test_data_path)
    testing_review = testing.Review
    testing_sentiment = testing.Sentiment
    for text, label in zip(testing_review, testing_sentiment):
        testing_texts.append(text)
        testing_labels.append(label)
    print("Finish loading testing data")
    logging.info("Finish loading testing data")

    print('prepare training and test sets')
    logging.info('Prepare training and test sets')

    train_dataset, validation_dataset,testing_dataset = IMDB_indexing(training_texts,training_labels,validation_texts,validation_labels,testing_texts,testing_labels,vocab= vocab)
    print('building vocab')

    # vocab = train_dataset.get_vocab()


    # vocab_size = len(vocab)
    # print('building vocab length',vocab_size)
    # logging.info('Build vocab')

    return train_dataset,validation_dataset,testing_dataset

def generate_batch(batch):
    """
    Output:
        text: the text entries in the data_batch are packed into a list and
            concatenated as a single tensor for the input of nn.EmbeddingBag.
        cls: a tensor saving the labels of individual text entries.
    """
    # check if the dataset if train or test
    if len(batch[0]) == 2:
        label = [entry[0] for entry in batch]

        # padding according to the maximum sequence length in batch
        text = [entry[1] for entry in batch]
        # text_length = [len(seq) for seq in text]
        text,text_length= pad_sequence(text, ksz = 256, batch_first=True)
        return text, text_length, label
    else:
        text = [entry for entry in batch]
        # text_length = [len(seq) for seq in text]
        text ,text_length= pad_sequence(text, ksz=256, batch_first=True)
        return text, text_length
def categorical_accuracy(preds, y):
    """
    Returns accuracy per batch, i.e. if you get 8/10 right, this returns 0.8, NOT 8
    """
    top_pred = preds.argmax(1, keepdim = True)
    correct = top_pred.eq(y.view_as(top_pred)).sum()
    acc = correct.float() / y.shape[0]
    return acc

def train(train_dataset,model,criterion,device,optimizer,lr_scheduler,epoche):
    model.train()
    epoch_loss = 0
    epoch_acc = 0
    # if epoche>1:
    #     model.embedding_layer.weight.requires_grad = False


    for i,(text, length,label) in tqdm(enumerate(train_dataset),total = len(train_dataset)):
        text_length = torch.Tensor(length)
        label = torch.tensor(label,dtype=torch.long)

        # lengths, indices = torch.sort(text_length, dim=0, descending=True)
        # text = torch.index_select(text, dim=0, index=indices)
        #
        # label = torch.index_select(label, dim=0, index=indices)
        text_length= text_length.to(device)
        text = text.to(device,dtype = torch.long)
        label =label.to(device)


        optimizer.zero_grad()
        output = model(text,text_length)
        loss = criterion(output,label)
        acc = categorical_accuracy(output, label)
        epoch_loss += loss.item()
        epoch_acc += acc.item()
        loss.backward()
        optimizer.step()
    lr_scheduler.step()
    return epoch_loss / len(train_dataset), epoch_acc / len(train_dataset)


def validate(validation_dataset, model, criterion, device):
    model.eval()

    epoch_loss = 0
    epoch_acc = 0

    for i,(text, length,label) in enumerate(validation_dataset):
        text_length = torch.Tensor(length)
        label = torch.tensor(label, dtype=torch.long)

        # lengths, indices = torch.sort(text_length, dim=0, descending=True)
        # text = torch.index_select(text, dim=0, index=indices)
        # label = torch.index_select(label, dim=0, index=indices)
        text_length = text_length.to(device)
        text = text.to(device,dtype = torch.long)
        label = label.to(device)

        with torch.no_grad():
            output = model(text,text_length)
        loss = criterion(output,label)
        acc = categorical_accuracy(output, label)
        epoch_loss += loss.item()
        epoch_acc += acc.item()
    return epoch_loss / len(validation_dataset), epoch_acc / len(validation_dataset)







def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--train_path',type=str,default='/home/dongxx/projects/def-mercer/dongxx/project/data/train.csv')
    parser.add_argument('--validation_path',type= str,default='/home/dongxx/projects/def-mercer/dongxx/project/data/valid.csv')
    parser.add_argument('--test_path',type= str,default='/home/dongxx/projects/def-mercer/dongxx/project/data/test.csv')

    parser.add_argument('--dropout', type=float, default=0.2)
    parser.add_argument('--embedding_dim', type=int, default=100)
    parser.add_argument('--num_epochs', type=int, default=16)
    parser.add_argument('--batch_sz', type=int, default=4)
    parser.add_argument('--lr', type=float, default=1e-3)

    parser.add_argument('--weight_decay', type=float, default=0.5)
    parser.add_argument('--scheduler_step_sz', type=int, default=5)
    parser.add_argument('--lr_gamma', type=float, default=0.1)
    parser.add_argument('--number_class', type=int, default=2)

    args = parser.parse_args()

    # device
    # device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    # dataset
    glove = torchtext.vocab.GloVe(name='6B', dim=100, unk_init=torch.Tensor.normal_)
    vocab = Vocab(glove.stoi,specials =[])
    print(vocab.itos[0])
    print(vocab.itos[1])
    print(vocab.itos[2])
    # train_dataset, validation_dataset, test_dataset, vocab, vocab_size = prepare_dateset(args.train_path,args.validation_path)
    train_dataset, validation_dataset,test_dataset, vocab_size = prepare_dateset(args.train_path,args.validation_path,args.test_path,vocab=vocab)
    # modelvocab_size,hidden_dim,n_layers,dropout,number_class,bidirectional,embedding_dim =10
    LSTM_model =LSTMBaseline(vocab_size = vocab_size,hidden_dim = config.HIDDEN_DIM, n_layers =config.N_LAYERS, dropout = args.dropout, number_class = args.number_class, bidirectional = True, embedding_dim =100)
    LSTM_model.to(device)
    #opt scheduler criterion
    optimizer = torch.optim.Adam(LSTM_model.parameters(), lr=args.lr)
    lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, gamma=args.lr_gamma, step_size=5)
    criterion = nn.CrossEntropyLoss()
    criterion.to(device)

    training = DataLoader(train_dataset,collate_fn = generate_batch, batch_size=args.batch_sz,shuffle=True)
    validation = DataLoader(validation_dataset, collate_fn= generate_batch, batch_size=args.batch_sz, shuffle=False)
    testing = DataLoader(test_dataset, collate_fn= generate_batch, batch_size=args.batch_sz, shuffle=False)
    #loading vocab




    LSTM_model.embedding_layer.weight.data.copy_(glove.vectors).to(device)
    LSTM_model.embedding_layer.weight.data[1] = torch.zeros(100)
    LSTM_model.embedding_layer.weight.data[0] = torch.zeros(100)


    LSTM_model.embedding_layer.weight.requires_grad = False
    # ret = glove.get_vecs_by_tokens(['<unk>'])
    # print(ret)

    best_loss = float('inf')
    print("training")
    for epoch in range(15):
        start_time = time.time()
        # print("training emebedding")


        train_loss, train_acc = train(training,LSTM_model,criterion,device,optimizer,lr_scheduler,epoch)
        # print("testing emebedding")
        valid_loss, valid_acc = validate(validation,LSTM_model,criterion,device)
        end_time = time.time()
        epoch_mins, epoch_secs = epoch_time(start_time, end_time)
        print(f'Epoch: {epoch + 1:02} | Epoch Time: {epoch_mins}m {epoch_secs}s')
        print(f'\tTrain Loss: {train_loss:.3f} | Train Acc: {train_acc * 100:.2f}%')
        print(f'\t Val. Loss: {valid_loss:.3f} |  Val. Acc: {valid_acc * 100:.2f}%')
        if valid_loss < best_loss:
            best_loss = valid_loss
            torch.save(LSTM_model.state_dict(), config.MODEL_Base_PATH)
    print("training done")

    print("testing")
    LSTM_model.load_state_dict(torch.load(config.MODEL_Base_PATH))
    test_loss, test_acc = validate(testing,LSTM_model,criterion,device)

    print(f'Test Loss: {test_loss:.3f} | Test Acc: {test_acc * 100:.2f}%')
    print("testing done")





if __name__ == "__main__":
    main()
from keras.layers import *
import jieba
import multiprocessing
import pandas as pd
from gensim.models import Word2Vec
import numpy as np
import keras.backend as K
from keras.callbacks import Callback, ModelCheckpoint
from keras.models import Model
from keras.utils.np_utils import to_categorical
from keras.preprocessing.text import Tokenizer
from keras.preprocessing.sequence import pad_sequences
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import classification_report, accuracy_score, f1_score
import ipykernel


def token(text):
    """
    实现分词
    :param text:文本
    :return:
    """
    return " ".join(jieba.cut(text))


def train_w2v(text_list=None, output_vector='data/w2v.txt'):
    """
    训练word2vec
    :param text_list:文本列表
    :param output_vector:词向量输出路径
    :return:
    """
    print("正在训练词向量。。。")
    corpus = [text.split() for text in text_list]
    model = Word2Vec(corpus, size=100, window=5, min_count=1, workers=multiprocessing.cpu_count())
    # 保存词向量
    model.wv.save_word2vec_format(output_vector, binary=False)


# sample.csv
# test_new.csv
# train.csv
train = pd.read_csv('data/train.csv', sep='\t')
test = pd.read_csv('data/test_new.csv')
sub = pd.read_csv('data/sample.csv')

# 数据处理 复制label为1文本
# index = train.label == 1
# print(index)
# train[index]
# train.['comment'] = train[index]['comment'].apply(lambda x: x +'。'+ x)
# 全量数据
train['id'] = [i for i in range(len(train))]
test['label'] = [-1 for i in range(len(test))]
df = pd.concat([train, test], sort=False)
df['token_text'] = df['comment'].apply(lambda x: token(x))
texts = df['token_text'].values.tolist()
train_w2v(texts)

# 构建词汇表
tokenizer = Tokenizer()
tokenizer.fit_on_texts(texts)
word_index = tokenizer.word_index
print("词语数量个数：{}".format(len(word_index)))

# 数据
EMBEDDING_DIM = 100
MAX_SEQUENCE_LENGTH = 100

#将每句话填充到100词
sequences = tokenizer.texts_to_sequences(texts)
data = pad_sequences(sequences, maxlen=MAX_SEQUENCE_LENGTH)

# 类别编码
x_train = data[:len(train)]
x_test = data[len(train):]
y_train = to_categorical(train['label'].values)
y_train = y_train.astype(np.int32)
print(y_train)


# 创建embedding_layer
def create_embedding(word_index, w2v_file):
    """

    :param word_index: 词语索引字典
    :param w2v_file: 词向量文件
    :return:
    """
    embedding_index = {}
    f = open(w2v_file, 'r', encoding='utf-8')
    next(f)  # 下一行
    for line in f:
        values = line.split()
        word = values[0]
        coefs = np.asarray(values[1:], dtype='float32')
        embedding_index[word] = coefs
    f.close()
    print("Total %d word vectors in w2v_file" % len(embedding_index))

    embedding_matrix = np.random.random(size=(len(word_index) + 1, EMBEDDING_DIM))
    for word, i in word_index.items():
        embedding_vector = embedding_index.get(word)
        if embedding_vector is not None:
            embedding_matrix[i] = embedding_vector
    embedding_layer = Embedding(len(word_index) + 1,
                                EMBEDDING_DIM, weights=[embedding_matrix],
                                input_length=MAX_SEQUENCE_LENGTH, trainable=True)
    return embedding_layer


def create_text_cnn():
    #
    sequence_input = Input(shape=(MAX_SEQUENCE_LENGTH,), dtype='int32')
    embedding_layer = create_embedding(word_index, 'data/w2v.txt')
    embedding_sequences = embedding_layer(sequence_input)
    conv1 = Conv1D(128, 5, activation='relu', padding='same')(embedding_sequences)
    pool1 = MaxPool1D(3)(conv1)
    conv2 = Conv1D(128, 5, activation='relu', padding='same')(pool1)
    pool2 = MaxPool1D(3)(conv2)
    conv3 = Conv1D(128, 5, activation='relu', padding='same')(pool2)
    pool3 = MaxPool1D(3)(conv3)
    flat = Flatten()(pool3)
    dense = Dense(128, activation='relu')(flat)
    preds = Dense(2, activation='softmax')(dense)
    model = Model(sequence_input, preds)
    return model


train_pred = np.zeros((len(train), 2))
test_pred = np.zeros((len(test), 2))

skf = StratifiedKFold(n_splits=5, random_state=52, shuffle=True)
for i, (train_index, valid_index) in enumerate(skf.split(x_train, train['label'])):
    print("n@:{}fold".format(i + 1))
    X_train = x_train[train_index]
    X_valid = x_train[valid_index]
    y_tr = y_train[train_index]
    y_val = y_train[valid_index]

    model = create_text_cnn()
    model.compile(loss='categorical_crossentropy',
                  optimizer='rmsprop',
                  metrics=['acc'])
    model.summary()#打印参数
    checkpoint = ModelCheckpoint(filepath='models/cnn_text_{}.h5'.format(i + 1),
                                 monitor='val_loss',
                                 verbose=1, save_best_only=True)
    history = model.fit(X_train, y_tr,
                        validation_data=(X_valid, y_val),
                        epochs=10, batch_size=32,
                        callbacks=[checkpoint])

    # model.load_weights('models/cnn_text.h5')
    train_pred[valid_index, :] = model.predict(X_valid)
    test_pred += model.predict(x_test)

labels = np.argmax(test_pred, axis=1)
sub['label'] = labels
sub.to_csv('result/cnn.csv', index=None)

# 训练数据预测结果
# 概率
oof_df = pd.DataFrame(train_pred)
train = pd.concat([train, oof_df], axis=1)
# 标签
labels = np.argmax(train_pred, axis=1)
train['pred'] = labels
# 分类报告
train.to_excel('result/train.xlsx', index=None)
print(classification_report(train['label'].values, train['pred'].values))
print(f1_score(train['label'].values, train['pred'].values))
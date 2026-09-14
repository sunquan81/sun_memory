# -*- coding: utf-8 -*-
"""本记忆体 · 英文词形归一（父令2026-08-14·"英文跟中文一样能存能取"）
零依赖轻量词干化：英文有词形变化（paint/painted/service/services），
中文没有——加词形归一让英文召回达到中文同等水平。
"""
import re

# 轻量 Porter 风格词干（规则版·零依赖）
_不规则 = {
    'is': 'be', 'was': 'be', 'were': 'be', 'been': 'be', 'are': 'be', 'am': 'be',
    'has': 'have', 'had': 'have', 'does': 'do', 'did': 'do',
    'went': 'go', 'gone': 'go', 'goes': 'go',
    'made': 'make', 'makes': 'make', 'said': 'say', 'says': 'say',
    'told': 'tell', 'tells': 'tell', 'saw': 'see', 'seen': 'see', 'sees': 'see',
    'came': 'come', 'comes': 'come', 'gave': 'give', 'gives': 'give',
    'took': 'take', 'takes': 'take', 'got': 'get', 'gets': 'get',
    'found': 'find', 'finds': 'find', 'knew': 'know', 'knows': 'know',
    'thought': 'think', 'thinks': 'think', 'bought': 'buy', 'buys': 'buy',
    'brought': 'bring', 'brings': 'bring', 'wrote': 'write', 'writes': 'write',
    'read': 'read', 'reads': 'read', 'ran': 'run', 'runs': 'run',
    'paid': 'pay', 'pays': 'pay', 'met': 'meet', 'meets': 'meet',
    'lost': 'lose', 'loses': 'lose', 'sent': 'send', 'sends': 'send',
    'built': 'build', 'builds': 'build', 'held': 'hold', 'holds': 'hold',
    'left': 'leave', 'leaves': 'leave', 'felt': 'feel', 'feels': 'feel',
    'kept': 'keep', 'keeps': 'keep', 'slept': 'sleep', 'sleeps': 'sleep',
    'spoke': 'speak', 'speaks': 'speak', 'broke': 'break', 'breaks': 'break',
    'chose': 'choose', 'chooses': 'choose', 'drove': 'drive', 'drives': 'drive',
    'ate': 'eat', 'eats': 'eat', 'fell': 'fall', 'falls': 'fall',
    'women': 'woman', 'men': 'man', 'children': 'child', 'people': 'person',
    'mice': 'mouse', 'feet': 'foot', 'teeth': 'tooth', 'geese': 'goose',
}

def 词干(word: str) -> str:
    """轻量词干化：复数/过去式/ing/比较级 归一到基础形式"""
    w = word.lower()
    if w in _不规则:
        return _不规则[w]
    if len(w) <= 3:
        return w
    # 复数 -ies → -y (cities→city)
    if w.endswith('ies') and len(w) > 4:
        return w[:-3] + 'y'
    # 复数 -es → 去es (boxes→box, watches→watch)
    if w.endswith('es'):
        # 保持 x/ch/sh/s 后的 e（boxes→box）
        stem = w[:-2]
        if stem.endswith(('x', 'ch', 'sh', 's', 'z')):
            return stem
        return w[:-1]  # 其他 -es 只去s (makes→make)
    # 复数 -s → 去s (services→service)
    if w.endswith('s') and not w.endswith('ss') and len(w) > 4:
        return w[:-1]
    # 过去式 -ied → -y (studied→study)
    if w.endswith('ied') and len(w) > 4:
        return w[:-3] + 'y'
    # 过去式 -ed → 去ed (painted→paint)
    if w.endswith('ed') and len(w) > 4:
        stem = w[:-2]
        # 双写辅音还原 (stopped→stop)
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            return stem[:-1]
        return stem
    # 进行时 -ing → 去ing (painting→paint)
    if w.endswith('ing') and len(w) > 5:
        stem = w[:-3]
        # 双写辅音还原 (running→run)
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            return stem[:-1]
        # -ying → -y (studying→study)
        if stem.endswith('y'):
            return stem
        # 去 e (making→make, having→have)
        if w.endswith('king') or w.endswith('ving') or w.endswith('ming') or w.endswith('ning'):
            return stem + 'e'
        return stem
    # 比较级/最高级 -er/-est (bigger→big, happier→happy)
    if w.endswith('er') and len(w) > 4:
        stem = w[:-2]
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            return stem[:-1]
        if stem.endswith('i'):
            return stem[:-1] + 'y'  # happier→happi→happy
        return stem
    if w.endswith('est') and len(w) > 5:
        stem = w[:-3]
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            return stem[:-1]
        if stem.endswith('i'):
            return stem[:-1] + 'y'  # happiest→happi→happy
        return stem
    return w

def 归一文本(text: str) -> str:
    """整段文本词形归一：每个英文词转词干"""
    def _repl(m):
        return 词干(m.group(0))
    return re.sub(r'[a-zA-Z]+', _repl, text)

if __name__ == '__main__':
    测试 = ['paint', 'painted', 'painting', 'service', 'services', 'fix', 'fixed',
           'go', 'went', 'gone', 'car', 'cars', 'study', 'studied', 'studying',
           'run', 'running', 'make', 'making', 'box', 'boxes', 'city', 'cities',
           'happy', 'happier', 'happiest']
    print('词干化测试:')
    for t in 测试:
        print(f'  {t} → {词干(t)}')
    print()
    print('句子归一:')
    print(归一文本('Caroline went to the LGBTQ support group, she painted a beautiful sunrise'))

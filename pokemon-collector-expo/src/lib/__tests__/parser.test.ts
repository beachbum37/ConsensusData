/// <reference types="node" />
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isEmpty, nameScore, parseCardText } from '../parser.ts';

test('modern card', () => {
  const c = parseCardText(['BASIC', 'Pikachu', 'HP 60', 'Gnaw 20', 'Weakness', 'Retreat', 'Illus. Naoki Saito', 'SVI EN 063/198 ●']);
  assert.equal(c.number, '63');
  assert.equal(c.setTotal, 198);
  assert.equal(c.hp, 60);
  assert.equal(c.names[0], 'Pikachu');
});

test('name and HP on one line', () => {
  const c = parseCardText(['STAGE 2', 'Charizard ex 330 HP', 'Evolves from Charmeleon', '125/197']);
  assert.equal(c.names[0], 'Charizard ex');
  assert.equal(c.hp, 330);
  assert.equal(c.number, '125');
  assert.equal(c.setTotal, 197);
});

test('vintage card with OCR slips', () => {
  const c = parseCardText(['Charizard', '120 HP', '4/IO2']);
  assert.equal(c.number, '4');
  assert.equal(c.setTotal, 102);
});

test('secret rare above printed total', () => {
  const c = parseCardText(['Mew ex', '232/091']);
  assert.equal(c.number, '232');
  assert.equal(c.setTotal, 91);
});

test('trainer gallery subset', () => {
  const c = parseCardText(['Zekrom', 'TG05/TG30']);
  assert.equal(c.number, 'TG05');
  assert.equal(c.setTotal, null);
});

test('black star promo', () => {
  assert.equal(parseCardText(['Pikachu V', 'SWSH061']).number, 'SWSH061');
});

test('rules text is not a name', () => {
  const c = parseCardText(['Search your deck for a card and put it into your hand.', "Professor's Research", 'Trainer']);
  assert.deepEqual(c.names, ["Professor's Research"]);
});

test('nothing readable', () => {
  assert.ok(isEmpty(parseCardText(['12', '@@'])));
});

test('fuzzy names', () => {
  assert.equal(nameScore('Pikachu', 'pikachu'), 1);
  assert.ok(nameScore('Pikachv', 'Pikachu') > 0.8);
  assert.ok(nameScore('Charizard', 'Charizard ex') >= 0.9);
  assert.ok(nameScore('Bulbasaur', 'Mewtwo') < 0.3);
});

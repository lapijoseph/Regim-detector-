import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Optional, List, Dict, Tuple
from pathlib import Path


DB_PATH = Path(__file__).parent / 'capitalure_journal.db'


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('long','short')),
            entry_price REAL NOT NULL,
            exit_price REAL,
            stop_loss REAL,
            take_profit REAL,
            position_size REAL,
            pips REAL,
            pnl REAL,
            r_multiple REAL,
            result TEXT CHECK(result IN ('win','loss','breakeven','open')),
            strategy TEXT DEFAULT 'Manual',
            regime_at_entry TEXT,
            regime_at_exit TEXT,
            tags TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            discipline_rating INTEGER DEFAULT 5 CHECK(discipline_rating BETWEEN 1 AND 10),
            emotion TEXT DEFAULT '',
            session TEXT DEFAULT '' CHECK(session IN ('','asia','london','ny','overlap')),
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS journal_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy TEXT NOT NULL,
            rule TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS journal_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric TEXT NOT NULL,
            target REAL NOT NULL,
            timeframe TEXT DEFAULT 'weekly',
            created_at TEXT DEFAULT (datetime('now'))
        );
    ''')
    conn.commit()
    conn.close()


class TradeJournal:
    def __init__(self):
        init_db()

    def add_trade(self, date: str, symbol: str, direction: str, entry_price: float,
                  exit_price: Optional[float] = None, stop_loss: Optional[float] = None,
                  take_profit: Optional[float] = None, position_size: Optional[float] = None,
                  strategy: str = 'Manual', regime_at_entry: Optional[str] = None,
                  notes: str = '', tags: str = '', discipline_rating: int = 5,
                  emotion: str = '', session: str = '') -> int:
        conn = get_db()
        pips = None
        pnl = None
        r_multiple = None
        result = 'open'

        if exit_price is not None:
            pip_size = self._pip_size(symbol)
            price_diff = (exit_price - entry_price) if direction == 'long' else (entry_price - exit_price)
            pips = round(price_diff / pip_size, 1)
            pip_value = self._pip_value(symbol, entry_price)
            pnl = round(pips * (position_size or 0) * pip_value, 2)
            if pips > 0:
                result = 'win'
            elif pips < 0:
                result = 'loss'
            else:
                result = 'breakeven'
            if stop_loss is not None:
                sl_pips = abs(entry_price - stop_loss) / pip_size
                r_multiple = round(pips / sl_pips, 2) if sl_pips > 0 else 0

        cursor = conn.execute('''
            INSERT INTO trades (date, symbol, direction, entry_price, exit_price,
                stop_loss, take_profit, position_size, pips, pnl, r_multiple,
                result, strategy, regime_at_entry, notes, tags,
                discipline_rating, emotion, session)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (date, symbol.upper(), direction, entry_price, exit_price,
              stop_loss, take_profit, position_size, pips, pnl, r_multiple,
              result, strategy, regime_at_entry, notes, tags,
              discipline_rating, emotion, session))
        conn.commit()
        trade_id = cursor.lastrowid
        conn.close()
        return trade_id

    def update_trade(self, trade_id: int, **kwargs):
        allowed = {'exit_price', 'stop_loss', 'take_profit', 'position_size',
                   'notes', 'tags', 'discipline_rating', 'emotion', 'session', 'strategy'}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return
        updates['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join(f'{k}=?' for k in updates)
        vals = list(updates.values()) + [trade_id]
        conn = get_db()
        conn.execute(f'UPDATE trades SET {set_clause} WHERE id=?', vals)
        conn.commit()
        conn.close()

    def close_trade(self, trade_id: int, exit_price: float):
        conn = get_db()
        trade = conn.execute('SELECT * FROM trades WHERE id=?', (trade_id,)).fetchone()
        if not trade or trade['result'] != 'open':
            conn.close()
            return
        symbol = trade['symbol']
        direction = trade['direction']
        entry = trade['entry_price']
        pos = trade['position_size'] or 0
        sl = trade['stop_loss']

        pip_size = self._pip_size(symbol)
        price_diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
        pips = round(price_diff / pip_size, 1)
        pip_value = self._pip_value(symbol, entry)
        pnl = round(pips * pos * pip_value, 2)

        if pips > 0:
            result = 'win'
        elif pips < 0:
            result = 'loss'
        else:
            result = 'breakeven'

        r_multiple = None
        if sl:
            sl_pips = abs(entry - sl) / pip_size
            r_multiple = round(pips / sl_pips, 2) if sl_pips > 0 else 0

        conn.execute('''UPDATE trades SET exit_price=?, pips=?, pnl=?, r_multiple=?,
            result=?, updated_at=datetime('now') WHERE id=?''',
            (exit_price, pips, pnl, r_multiple, result, trade_id))
        conn.commit()
        conn.close()

    def delete_trade(self, trade_id: int):
        conn = get_db()
        conn.execute('DELETE FROM trades WHERE id=?', (trade_id,))
        conn.commit()
        conn.close()

    def get_trade(self, trade_id: int) -> Optional[Dict]:
        conn = get_db()
        row = conn.execute('SELECT * FROM trades WHERE id=?', (trade_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_trades(self, symbol: Optional[str] = None,
                   result_filter: Optional[str] = None,
                   strategy: Optional[str] = None,
                   days_back: Optional[int] = None,
                   limit: int = 100) -> pd.DataFrame:
        query = 'SELECT * FROM trades WHERE 1=1'
        params = []
        if symbol:
            query += ' AND symbol=?'; params.append(symbol.upper())
        if result_filter:
            query += ' AND result=?'; params.append(result_filter)
        if strategy:
            query += ' AND strategy=?'; params.append(strategy)
        if days_back:
            from datetime import datetime, timedelta
            cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
            query += ' AND date>=?'; params.append(cutoff)
        query += ' ORDER BY date DESC LIMIT ?'; params.append(limit)
        conn = get_db()
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df

    def get_stats(self, days_back: Optional[int] = None) -> Dict:
        df = self.get_trades(days_back=days_back)
        df_closed = df[df['result'].isin(['win', 'loss', 'breakeven'])].copy()
        total = len(df_closed)
        if total == 0:
            return {'total_trades': 0, 'message': 'No closed trades yet'}
        wins = df_closed[df_closed['result'] == 'win']
        losses = df_closed[df_closed['result'] == 'loss']
        n_wins = len(wins)
        n_losses = len(losses)
        win_rate = round(n_wins / total * 100, 1) if total > 0 else 0
        total_pnl = round(df_closed['pnl'].sum(), 2) if 'pnl' in df_closed.columns else 0
        avg_win = round(wins['pnl'].mean(), 2) if n_wins > 0 else 0
        avg_loss = round(losses['pnl'].mean(), 2) if n_losses > 0 else 0
        total_loss = round(losses['pnl'].sum(), 2) if n_losses > 0 else 0
        profit_factor = round(abs(wins['pnl'].sum() / total_loss), 2) if total_loss != 0 and n_losses > 0 else float('inf')
        avg_r = round(df_closed['r_multiple'].mean(), 2) if 'r_multiple' in df_closed.columns else 0
        expectancy = round((win_rate / 100 * avg_win + (1 - win_rate / 100) * avg_loss), 2) if avg_loss else 0
        best_trade = round(df_closed['pnl'].max(), 2) if 'pnl' in df_closed.columns else 0
        worst_trade = round(df_closed['pnl'].min(), 2) if 'pnl' in df_closed.columns else 0

        return {
            'total_trades': total,
            'wins': n_wins,
            'losses': n_losses,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_r': avg_r,
            'expectancy': expectancy,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_discipline': round(df_closed['discipline_rating'].mean(), 1) if 'discipline_rating' in df_closed.columns else 0,
        }

    def get_strategies(self) -> List[str]:
        conn = get_db()
        rows = conn.execute('SELECT DISTINCT strategy FROM trades ORDER BY strategy').fetchall()
        conn.close()
        return [r['strategy'] for r in rows]

    def get_symbols(self) -> List[str]:
        conn = get_db()
        rows = conn.execute('SELECT DISTINCT symbol FROM trades ORDER BY symbol').fetchall()
        conn.close()
        return [r['symbol'] for r in rows]

    def export_csv(self, path: str):
        df = self.get_trades(limit=10000)
        df.to_csv(path, index=False)
        return path

    @staticmethod
    def _pip_size(symbol: str) -> float:
        if symbol in ('BTC-USD','ETH-USD','BTCUSD','ETHUSD'):
            return 1.0
        if symbol in ('XAUUSD','XAGUSD','GC=F','SI=F'):
            return 0.01
        if 'JPY' in symbol:
            return 0.01
        return 0.0001

    @staticmethod
    def _pip_value(symbol: str, price: float) -> float:
        pip_size = TradeJournal._pip_size(symbol)
        if symbol in ('BTC-USD','ETH-USD','BTCUSD','ETHUSD'):
            return pip_size
        if symbol in ('XAUUSD','XAGUSD','GC=F','SI=F'):
            return pip_size * 100
        if 'JPY' in symbol:
            return pip_size / price * 100000
        return pip_size * 100000


if __name__ == '__main__':
    init_db()
    print(f'Journal DB ready at: {DB_PATH}')

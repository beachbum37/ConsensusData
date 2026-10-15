package com.pokecollector.app

import android.app.Application
import com.pokecollector.app.data.CardRepository
import com.pokecollector.app.data.api.PokemonTcgApi
import com.pokecollector.app.data.db.AppDatabase

class PokeCollectorApp : Application() {
    val repository: CardRepository by lazy {
        CardRepository(PokemonTcgApi.create(), AppDatabase.create(this).collection())
    }
}

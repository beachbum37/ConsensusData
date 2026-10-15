package com.pokecollector.app.data.api

import com.pokecollector.app.BuildConfig
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Response
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query
import java.util.concurrent.TimeUnit

/** https://docs.pokemontcg.io — card data plus TCGplayer and Cardmarket prices. */
interface PokemonTcgApi {
    @GET("v2/cards")
    suspend fun search(
        @Query("q") query: String,
        @Query("pageSize") pageSize: Int = 30,
        @Query("orderBy") orderBy: String = "-set.releaseDate",
        @Query("select") select: String = FIELDS,
    ): CardListResponse

    @GET("v2/cards/{id}")
    suspend fun card(
        @Path("id") id: String,
        @Query("select") select: String = FIELDS,
    ): CardResponse

    companion object {
        private const val FIELDS =
            "id,name,number,rarity,supertype,hp,set,images,tcgplayer,cardmarket"

        fun create(): PokemonTcgApi {
            val client = OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .addInterceptor { chain ->
                    val key = BuildConfig.POKEMON_TCG_API_KEY
                    val req = chain.request().newBuilder()
                    if (key.isNotBlank()) req.header("X-Api-Key", key)
                    chain.proceed(req.build())
                }
                .addInterceptor(RetryOnServerError())
                .build()
            val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
            return Retrofit.Builder()
                .baseUrl("https://api.pokemontcg.io/")
                .client(client)
                .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
                .build()
                .create(PokemonTcgApi::class.java)
        }
    }
}

/** The public API returns sporadic 500/502s under load; a couple of quick retries clears most. */
private class RetryOnServerError(private val attempts: Int = 4) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        var response = chain.proceed(chain.request())
        var tries = 1
        while (response.code in setOf(500, 502, 503, 504) && tries < attempts) {
            response.close()
            Thread.sleep(400L * tries)
            response = chain.proceed(chain.request())
            tries++
        }
        return response
    }
}

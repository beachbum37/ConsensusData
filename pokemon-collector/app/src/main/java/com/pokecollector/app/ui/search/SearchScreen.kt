package com.pokecollector.app.ui.search

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.pokecollector.app.data.CardRepository
import com.pokecollector.app.data.api.ApiCard
import com.pokecollector.app.ui.CardRow
import com.pokecollector.app.ui.repoViewModelFactory
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

data class SearchState(
    val loading: Boolean = false,
    val results: List<ApiCard> = emptyList(),
    val message: String? = "Search by name (\"Charizard ex\"), number (\"4/102\"), or both.",
)

class SearchViewModel(private val repo: CardRepository) : ViewModel() {
    val state = MutableStateFlow(SearchState())
    private var job: Job? = null

    fun search(text: String) {
        job?.cancel()
        job = viewModelScope.launch {
            state.value = SearchState(loading = true, message = null)
            state.value = runCatching { repo.search(text) }.fold(
                { SearchState(results = it, message = if (it.isEmpty()) "No cards found." else null) },
                { SearchState(message = "Couldn't reach the card database. Check your connection.") },
            )
        }
    }
}

@Composable
fun SearchScreen(onOpenCard: (String) -> Unit) {
    val vm: SearchViewModel = viewModel(factory = repoViewModelFactory(::SearchViewModel))
    val state by vm.state.collectAsStateWithLifecycle()
    var query by rememberSaveable { mutableStateOf("") }

    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            placeholder = { Text("Card name or number") },
            leadingIcon = { Icon(Icons.Default.Search, null) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { vm.search(query) }),
        )
        when {
            state.loading -> Box(Modifier.fillMaxWidth().padding(32.dp), Alignment.Center) { CircularProgressIndicator() }
            state.message != null -> Text(
                state.message!!,
                Modifier.fillMaxWidth().padding(32.dp),
                textAlign = TextAlign.Center,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            else -> LazyColumn {
                items(state.results, key = { it.id }) { card ->
                    CardRow(card, onClick = { onOpenCard(card.id) })
                    HorizontalDivider(Modifier.padding(start = 80.dp))
                }
            }
        }
    }
}
